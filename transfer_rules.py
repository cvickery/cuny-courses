# Two modes of operation:
#   1. Create a list of all course_ids that are part of transfer rules, but do not appear in the catalog.
#   2. Clear and re-populate the transfer_rules table.

import psycopg2
import csv
import os
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--debug', '-d', action='store_true')
parser.add_argument('--generate', '-g', action='store_true')
parser.add_argument('--progress', '-p', action='store_true')
parser.add_argument('--report', '-r', action='store_true')
args = parser.parse_args()

# Get most recent transfer_rules file
all_files = [x for x in os.listdir('./queries/') if x.startswith('QNS_CV_SR_TRNS_INTERNAL_RULES')]
the_file = sorted(all_files, reverse=True)[0]
if args.report:
  print('Transfer rules file:', the_file)

known_bad_filename = 'known_bad_ids.{}.log'.format(os.getenv('HOSTNAME').split('.')[0])
db = psycopg2.connect('dbname=cuny_courses')
cursor = db.cursor()
if args.generate:
  baddies = open(known_bad_filename, 'w')
  bad_set = set()
  with open('./queries/' + the_file) as csvfile:
    csv_reader = csv.reader(csvfile)
    cols = None
    row_num = 0
    for row in csv_reader:
      row_num += 1
      if args.progress and row_num % 10000 == 0:
        print('row {}\r'.format(row_num), end='', file=sys.stderr)
      if cols == None:
        row[0] = row[0].replace('\ufeff', '')
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
        if args.debug:
          print(cols)
          for col in cols:
            print('{} = {}; '.format(col, cols.index(col), end = ''))
          print()
      else:
        if len(row) != len(cols):
          print('\nrow {} len(cols) = {} but len(rows) = {}'.format(row_num, len(cols), len(row)))
        source_course_id = int(row[cols.index('source_course_id')])
        destination_course_id = int(row[cols.index('destination_course_id')])
        if source_course_id not in bad_set:
          cursor.execute("select course_id from courses where course_id = {}".format(source_course_id))
          if cursor.rowcount == 0:
            bad_set.add(source_course_id)
            baddies.write('{} src\n'.format(source_course_id))
        if destination_course_id not in bad_set:
          cursor.execute("select course_id from courses where course_id = {}".format(destination_course_id))
          if cursor.rowcount == 0:
            bad_set.add(destination_course_id)
            baddies.write('{} dst\n'.format(destination_course_id))
  baddies.close()
else:
  conflicts = open('conflicts.{}.log'.format(os.getenv('HOSTNAME').split('.')[0]), 'w')
  cursor.execute('drop table if exists transfer_rules cascade')
  cursor.execute("""
      create table transfer_rules (
        source_course_id integer references courses,
        source_institution text references institutions,
        source_discipline text,
        source_catalog_number text,
        rule_priority integer,
        rule_group integer,
        rule_group_sequence integer,
        min_source_units real,
        max_source_units real,
        min_gpa real,
        max_gpa real,
        destination_course_id integer references courses,
        destination_institution text references institutions,
        destination_discipline text,
        destination_catalog_number text,
        taken_destination_units real,
        min_destination_units real,
        max_destination_units real,
        status integer default 0 references transfer_rule_status,
        primary key (source_course_id, rule_priority, rule_group, destination_course_id))
      """)

  known_bad_ids = [int(id.split(' ')[0]) for id in open(known_bad_filename)]
  known_institutions = ['BAR01', 'BCC01', 'BKL01', 'BMC01', 'CSI01', 'CTY01', 'GRD01', 'HOS01',
                        'HTR01', 'JJC01', 'KCC01', 'LAG01', 'LAW01', 'LEH01', 'MEC01', 'MED01',
                        'NCC01', 'NYT01', 'QCC01', 'QNS01', 'SPH01', 'SPS01', 'YRK01']
  num_rules = 0
  num_conflicts = 0
  with open('./queries/' + the_file) as csvfile:
    csv_reader = csv.reader(csvfile)
    cols = None
    row_num = 0;
    for row in csv_reader:
      if cols == None:
        row[0] = row[0].replace('\ufeff', '')
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
        if args.debug:
          print(cols)
          for col in cols:
            print('{} = {}; '.format(col, cols.index(col), end = ''))
            print()
      else:
        row_num += 1
        if args.progress and row_num % 10000 == 0: print('row {}\r'.format(row_num),
                                                         end='',
                                                         file=sys.stderr)
        source_institution = row[cols.index('source_institution')]
        destination_institution = row[cols.index('destination_institution')]
        source_course_id = int(row[cols.index('source_course_id')])
        destination_course_id = int(row[cols.index('destination_course_id')])
        rule_priority = int(row[cols.index('transfer_priority')])
        rule_group = int(row[cols.index('src_equivalency_component')])
        rule_group_sequence = int(row[cols.index('equivalency_sequence_num')])
        if source_course_id in known_bad_ids or destination_course_id in known_bad_ids:
          continue
        if source_institution not in known_institutions:
          conflicts.write('Unknown institution: {}\n'.format(source_institution))
          continue
        if destination_institution not in known_institutions:
          conflicts.write('Unknown institution: {}\n'.format(destination_institution))
          continue
        q = """
            insert into transfer_rules values(
            {}, -- source_course_id integer references courses,
            '{}', -- source_institution text references institutions,
            '{}', -- source_discipline text,
            '{}', -- source_catalog_number text,
            {}, -- rule_priority integer,
            {}, -- rule_group integer,
            {}, -- rule_group_sequence integer,
            {}, -- min_source_units real,
            {}, -- max_source_units real,
            {}, -- min_gpa real,
            {}, -- max_gpa real,
            {}, -- destination_course_id integer references courses,
            '{}', -- destination_institution text references institutions,
            '{}', -- destination_discipline text,
            '{}', -- destination_catalog_number text,
            {}, -- taken_destination_units real,
            {}, -- min_destination_units real,
            {}  -- max_destination_units real,
            )
            on conflict(source_course_id,
                        rule_priority,
                        rule_group,
                        destination_course_id) do nothing
            """.format(
            source_course_id,
            source_institution,
            row[cols.index('source_discipline')],
            row[cols.index('source_catalog_num')],
            rule_priority,
            rule_group,
            rule_group_sequence,
            float(row[cols.index('src_min_units')]),
            float(row[cols.index('src_max_units')]),
            float(row[cols.index('min_grade_pts')]),
            float(row[cols.index('max_grade_pts')]),
            destination_course_id,
            destination_institution,
            row[cols.index('destination_discipline')],
            row[cols.index('destination_catalog_num')],
            float(row[cols.index('units_taken')]),
            float(row[cols.index('dest_min_units')]),
            float(row[cols.index('dest_max_units')]))
        cursor.execute(q)
        num_rules += 1
        if cursor.rowcount == 0:
          num_conflicts += 1
          conflicts.write(
'-- {:06} {:5} {:7} {:8} {:2} {:3} {:2} {:6.3} {:6.3} {:6.3} {:6.3} {:06} {:5} {:5} {:8}\n'.format(
                                                          source_course_id,
                                                          source_institution,
                                                          row[cols.index('source_discipline')],
                                                          row[cols.index('source_catalog_num')],
                                                          rule_priority,
                                                          rule_group,
                                                          rule_group_sequence,
                                                          float(row[cols.index('src_min_units')]),
                                                          float(row[cols.index('src_max_units')]),
                                                          float(row[cols.index('min_grade_pts')]),
                                                          float(row[cols.index('max_grade_pts')]),
                                                          destination_course_id,
                                                          destination_institution,
                                                          row[cols.index('destination_discipline')],
                                                          row[cols.index('destination_catalog_num')]
                                                          )
          )
          cursor.execute("""select * from transfer_rules
                            where source_course_id = {}
                              and rule_priority = {}
                              and rule_group = {}
                              and destination_course_id = {}
                         """.format(source_course_id,
                                    rule_priority,
                                    rule_group,
                                    destination_course_id))
          for row in cursor.fetchall():
            conflicts.write (
'++ {:06} {:5} {:7} {:8} {:2} {:3} {:2} {:6.3} {:6.3} {:6.3} {:6.3} {:06} {:5} {:5} {:8}\n'.format(
                                                          row[0],
                                                          row[1],
                                                          row[2],
                                                          row[3],
                                                          row[4],
                                                          row[5],
                                                          row[6],
                                                          row[7],
                                                          row[8],
                                                          row[9],
                                                          row[10],
                                                          row[11],
                                                          row[12],
                                                          row[13],
                                                          row[14]))
    if args.report:
      cursor.execute('select count(*) from transfer_rules')
      num_inserted = cursor.fetchone()[0]
      num_ignored = num_rules - num_inserted
      print('Given {} transfer rules: kept {}; rejected {} ({} conflicts).'.format(num_rules,
                                                                                   num_inserted,
                                                                                   num_ignored,
                                                                                   num_conflicts))
    db.commit()
    db.close()
    conflicts.close()