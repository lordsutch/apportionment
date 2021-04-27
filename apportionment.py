#!/usr/bin/env python3

# Apportionment calculations using various methods
#
# Copyright (c) 2021 Christopher N. Lawrence <lordsutch@gmail.com>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import argparse
import math
import numpy as np
import pandas as pd
import sys


def equal_proportions(data: pd.DataFrame, seats: int,
                      no_losers=False, divisor_type='huntington-hill',
                      **kwargs) -> pd.DataFrame:
    total_population = data['POPULATION'].sum()
    
    # Each state gets one seat to start
    data["SEATS"] = 1

    while ((seatcount := data.SEATS.sum()) < seats or
           no_losers and (data.SEATS < data.APP2010).any()):
        # Stolen from https://en.wikipedia.org/wiki/Highest_averages_method
        if divisor_type == 'jefferson':
            divisor = data.SEATS+1
        elif divisor_type == 'webster':
            divisor = (data.SEATS*2)+1
        elif divisor_type == 'imperiali':
            divisor = (data.SEATS/2)+1
        elif divisor_type == 'danish':
            divisor = (data.SEATS*3)+1
        elif divisor_type == 'hamilton':
            divisor = data.SEATS
        else: # Huntington-Hill, default
            divisor = np.sqrt(data.SEATS*(data.SEATS+1))

        data['PRIORITY'] = data.POPULATION / divisor
        state_maxpri = data.PRIORITY.idxmax()
        maxpri = data.PRIORITY.max()
        data.loc[state_maxpri, 'SEATS'] += 1
        print(f'{seatcount+1:4d} {data.SEATS[state_maxpri]:2d} {state_maxpri:30} {maxpri:12.3f}', file=sys.stderr)

    # Sanity check
    assert no_losers or data.SEATS.sum() == seats

    return pd.DataFrame(dict(POPULATION=data.POPULATION, SEATS=data.SEATS))


def largest_remainders(data: pd.DataFrame, seats: int,
                       no_losers=False, quota_type='hare',
                       **kwargs) -> pd.DataFrame:
    if no_losers:
        while 1:
            # Solve this iteratively... otherwise I think we might run into the
            # Alabama paradox
            result = largest_remainders(data, seats, no_losers=False)
            if (result.SEATS < data.APP2010).any():
                seats += 1
            else:
                print(f'{seats} seats required for no losers.',
                      file=sys.stderr)
                return result
    
    total_population = data['POPULATION'].sum()

    if quota_type == 'droop':
        quota = math.floor(total_population / (seats+1)) + 1
    elif quota_type == 'hagenbach-bischoff':
        quota = math.floor(total_population / (seats+1))
    elif quota_type == 'imperiali':
        quota = math.floor(total_population / (seats+2))
    else:
        # Hare/Hamilton quota (default)
        quota = math.floor(total_population / seats)

    # Each state gets the total population / seats to start
    # with a minimum of 1 seat
    data["SEATS"] = data.POPULATION // quota # Use integer division
    data.loc[data.SEATS < 1, 'SEATS'] = 1

    remaining_seats = int(seats - data.SEATS.sum())

    remainders = (data.POPULATION/quota) - data.SEATS
    sorted_remainders = remainders.sort_values(ascending=False)
    print(sorted_remainders, remaining_seats, file=sys.stderr)
    states_to_add = sorted_remainders.iloc[:remaining_seats]
    print(states_to_add, file=sys.stderr)

    data.loc[states_to_add.index, 'SEATS'] += 1

    # Sanity check
    assert data.SEATS.sum() == seats

    return pd.DataFrame(dict(POPULATION=data.POPULATION, SEATS=data.SEATS.astype(int)))


def main() -> None:
    parser = argparse.ArgumentParser('calculate apportionment tables')
    seat_group = parser.add_mutually_exclusive_group(required=False)
    seat_group.add_argument('--seats', '-s', type=int, default=435,
                            help='number of seats to apportion (default: 435)')
    seat_group.add_argument('--cube-root', '-c', action='store_true',
                            help='use cube root rule to decide number of seats')
    seat_group.add_argument('--wyoming-rule', '-w', action='store_true',
                            help='use "Wyoming rule" (smallest state entitled to exactly one seat) to decide number of seats')
    seat_group.add_argument('--quota', '-q', type=int,
                            help='use a (rough) population quota per seat to decide number of seats')
    parser.add_argument('--no-losers', action='store_true',
                        help='make no states lose seats vs. 2010; seats will be treated as a minimum')
    method_group = parser.add_mutually_exclusive_group(required=False)
    method_group.add_argument('--equal-proportions', '--highest-averages',
                              dest='app_method',
                              const=equal_proportions, action='store_const',
                              default=equal_proportions,
                              help='use the equal proportions method (default)')
    method_group.add_argument('--largest-remainders', dest='app_method',
                              const=largest_remainders, action='store_const',
                              help='use the largest remainders method')
    parser.add_argument('--divisor', '-D',
                        choices=('huntington-hill', 'jefferson', 'webster',
                                 'imperiali', 'adams', 'hamilton', 'danish'),
                        default='huntington-hill',
                        help='divisor to use for highest averages (default: Huntington-Hill)')
    parser.add_argument('--quota-method', '-Q', dest='quota_type',
                        choices=('hare', 'droop', 'hagenbach-bischoff',
                                 'imperiali'),
                        default='hare',
                        help='quota formula to use for largest remainders (default: Hare-Hamilton)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='output file (default: stdout)')
    parser.add_argument('input', default='apportionment-2020-table01.csv',
                        metavar='INPUT', nargs='?',
                        help='input file with apportionment table', type=str)
    
    args = parser.parse_args()

    data = pd.read_csv(args.input, index_col=0)
    data['APP2010'] = data.APP2020 - data.APPCHANGE

    if args.cube_root:
        seats = math.pow(data.POPULATION.sum(), 1/3)
    elif args.wyoming_rule:
        seats = data.POPULATION.sum() // data.POPULATION.min()
    elif args.quota:
        seats = data.POPULATION.sum() // args.quota
    else:
        seats = args.seats

    if not args.no_losers:
        print(f'Apportioning {seats} seats...', file=sys.stderr)
    else:
        print('Ensuring all states keep existing seats...', file=sys.stderr)
    
    result = args.app_method(data, seats, args.no_losers,
                             quota_type=args.quota_type,
                             divisor_type=args.divisor)

    result['Difference2020'] = result.SEATS - data.APP2020
    result['Difference2010'] = result.SEATS - data.APP2010

    result.to_csv(args.output or sys.stdout)
    

if __name__ == '__main__':
    main()
