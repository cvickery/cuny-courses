# Two modes of operation:
#   1. Create a list of all course_ids that are part of transfer rules, but which do not appear in
#   the catalog.
#   2. Clear and re-populate the rule_groups, source_courses, and destination_courses tables.

import psycopg2
import csv
import os
import sys
import argparse
from collections import namedtuple
from datetime import date

parser = argparse.ArgumentParser()
parser.add_argument('--debug', '-d', action='store_true')
parser.add_argument('--generate', '-g', action='store_true')
parser.add_argument('--progress', '-p', action='store_true')
parser.add_argument('--report', '-r', action='store_true')
args = parser.parse_args()

db = psycopg2.connect('dbname=cuny_courses')
cursor = db.cursor()

# Get most recent transfer_rules query file
the_file = './latest_queries/QNS_CV_SR_TRNS_INTERNAL_RULES.csv'
file_date = date\
      .fromtimestamp(os.lstat(the_file).st_mtime).strftime('%Y-%m-%d')

cursor.execute("""
               update updates
               set update_date = '{}', file_name = '{}'
               where table_name = 'rules'""".format(file_date, the_file))

if args.report:
  print('Transfer rules query file: {} {}'.format(file_date, the_file))

num_lines = sum(1 for line in open(the_file))

known_bad_filename = 'known_bad_ids.{}.log'.format(os.getenv('HOSTNAME').split('.')[0])

# There be some garbage institution "names" in the transfer_rules
cursor.execute("""select code as institution
                  from institutions
                  group by institution
                  order by institution""")
known_institutions = [inst[0] for inst in cursor.fetchall()]

if args.generate:
  """
      Generate list of bad course_ids referenced in the rows of the transfer rules query
  """
  baddies = open(known_bad_filename, 'w')
  bad_set = set()
  with open(the_file) as csvfile:
    csv_reader = csv.reader(csvfile)
    cols = None
    row_num = 0
    for row in csv_reader:
      row_num += 1
      if args.progress and row_num % 10000 == 0:
        print('row {:,}/{:,}\r'.format(row_num, num_lines), end='', file=sys.stderr)
      if cols == None:
        row[0] = row[0].replace('\ufeff', '')
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
        Record = namedtuple('Record', cols)
        if args.debug:
          print(cols)
          for col in cols:
            print('{} = {}; '.format(col, cols.index(col), end = ''))
          print()
      else:
        if len(row) != len(cols):
          print('\nrow {} len(cols) = {} but len(rows) = {}'.format(row_num, len(cols), len(row)))
          continue
        record = Record._make(row)
        if record.source_institution not in known_institutions or \
           record.destination_institution not in known_institutions:
          continue
        source_course_id = int(record.source_course_id)
        destination_course_id = int(record.destination_course_id)
        if source_course_id not in bad_set:
          cursor.execute("""select course_id
                            from courses
                            where course_id = {}""".format(source_course_id))
          if cursor.rowcount == 0:
            bad_set.add(source_course_id)
            baddies.write('{} src\n'.format(source_course_id))
        if destination_course_id not in bad_set:
          cursor.execute("""select course_id
                            from courses
                            where course_id = {}""".format(destination_course_id))
          if cursor.rowcount == 0:
            bad_set.add(destination_course_id)
            baddies.write('{} dst\n'.format(destination_course_id))
  baddies.close()
else:
  """ Populate the three rule information tables
  """
  conflicts = open('conflicts.{}.log'.format(os.getenv('HOSTNAME').split('.')[0]), 'w')

  known_bad_ids = [int(id.split(' ')[0]) for id in open(known_bad_filename)]
  # Clear the three tables
  cursor.execute('truncate source_courses, destination_courses, rule_groups')

  num_groups = 0
  num_source_courses = 0
  num_destination_courses = 0

  with open(the_file) as csvfile:
    csv_reader = csv.reader(csvfile)
    cols = None
    row_num = 0;
    for row in csv_reader:
      if cols == None:
        row[0] = row[0].replace('\ufeff', '')
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
        Record = namedtuple('Record', cols);
        if args.debug:
          print(cols)
          for col in cols:
            print('{} = {}; '.format(col, cols.index(col), end = ''))
            print()
      else:
        row_num += 1
        if args.progress and row_num % 10000 == 0: print('row {:,}/{:,}\r'.format(row_num,
                                                                                  num_lines),
                                                         end='',
                                                         file=sys.stderr)
        record = Record._make(row)

        src_institution = record.source_institution
        if src_institution not in known_institutions:
          conflicts.write('Unknown institution: {}\n'.format(src_institution))
          continue
        dest_institution = record.destination_institution
        if dest_institution not in known_institutions:
          conflicts.write('Unknown institution: {}\n'.format(dest_institution))
          continue

        # Assemble the components of the rule group
        source_course_id = int(record.source_course_id)
        destination_course_id = int(record.destination_course_id)
        if source_course_id in known_bad_ids or destination_course_id in known_bad_ids:
          continue
        cursor.execute("""select institution, discipline
                          from courses
                          where course_id = {}""".format(source_course_id))
        source_institution, source_discipline = cursor.fetchone()
        if source_institution != src_institution:
          conflicts.write("""Source institution ({}) != course institution ({})\n{}\n"""\
                          .format(src_instituion, source_instution, record))
        cursor.execute("""select institution
                            from courses
                           where course_id = {}""".format(destination_course_id))
        destination_institution = cursor.fetchone()[0]
        if destination_institution != dest_institution:
          conflicts.write("""Destination institution ({}) != course institution ({})\n{}\n"""\
                          .format(dest_institution, destination_institution, record))
        rule_group_number = int(record.src_equivalency_component)
        min_gpa = float(record.min_grade_pts)
        max_gpa = float(record.max_grade_pts)
        transfer_credits = float(record.units_taken)

        # Create or look up the rule group
        cursor.execute("""
                       insert into rule_groups values(
                       '{}', '{}', {}, '{}') on conflict do nothing
                       """.format(source_institution,
                                  source_discipline,
                                  rule_group_number,
                                  destination_institution))
        num_groups += cursor.rowcount
        # if cursor.rowcount == 0:
        #   cursor.execute("""
        #                  select *
        #                  from rule_groups
        #                  where source_institution = '{}'
        #                  and discipline = '{}'
        #                  and group_number = {}
        #                  and destination_institution ='{}'
        #                  """.format(source_institution,
        #                             source_discipline,
        #                             rule_group_number,
        #                             destination_institution))
        #   assert cursor.rowcount == 1, """select rule_group returned {} values
        #                                """.format(cursor.rowcount)
        # rule_group_id = cursor.fetchone()[0]

        # Add the source course
        cursor.execute("""
                       insert into source_courses values(default, '{}', '{}', {}, '{}', {}, {}, {})
                       on conflict do nothing
                       """.format(source_institution,
                                  source_discipline,
                                  rule_group_number,
                                  destination_institution,
                                  source_course_id,
                                  min_gpa,
                                  max_gpa))
        num_source_courses += cursor.rowcount
        # Add the destination course
        cursor.execute("""
                       insert into destination_courses values(default, '{}', '{}', {}, '{}', {}, {})
                       on conflict do nothing
                       """.format(source_institution,
                                  source_discipline,
                                  rule_group_number,
                                  destination_institution,
                                  destination_course_id,
                                  transfer_credits))
        num_destination_courses += cursor.rowcount

    if args.report:
      print("""\n{:,} Groups\n{:,} Source courses\n{:,} Destination courses
            """.format(num_groups, num_source_courses, num_destination_courses))
    db.commit()
    db.close()
    conflicts.close()