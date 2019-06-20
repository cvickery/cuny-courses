#! /usr/local/bin/python3
""" Some queries have been coming in truncated. This utility checks the files in queries for
    emptyness and compares sizes with the corresponding files in latest_queries for size differences
    of 10% or more.
"""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='store_true')
args = parser.parse_args()

new_queries = Path('/Users/vickery/CUNY_Courses/queries')
previous_queries = Path('/Users/vickery/CUNY_Courses/latest_queries/')


for previous_query in previous_queries.glob('*.csv'):
  new_query = [q for q in new_queries.glob(f'{previous_query.stem}*.csv')]
  if len(new_query) == 0:
    exit(f'No new query for {previous_query.name}')
  assert len(new_query) == 1, f'{len(new_query)} matches for {previous_query.name}'
  new_query = new_query[0]
  previous_size = previous_query.stat().st_size
  new_size = new_query.stat().st_size
  if new_size == 0:
    exit(f'{new_query.name} has zero bytes')
  if abs(previous_size - new_size) > 0.1 * previous_size:
    exit('{} ({}) differs from {} ({}) by more than 10%'
         .format(new_query.name, new_size, previous_query.name, previous_size))
  if args.verbose:
    print(f'{new_query.name} compares favorably to {previous_query.name}')
# No problems detected
exit(0)
