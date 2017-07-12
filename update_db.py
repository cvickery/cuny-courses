from openpyxl import load_workbook
import sqlite3
import csv
import argparse

from datetime import date
import os
import re

parser = argparse.ArgumentParser()
parser.add_argument('--debug', '-d', action='store_true')
args = parser.parse_args()

db = sqlite3.connect('courses.db')
cur = db.cursor()
cur.execute('select code from institutions')
all_colleges = [x[0] for x in cur.fetchall()]

all_files = [x for x in os.listdir('.') if x.endswith('.csv')]
# Find most recent catalog, requisite, and attribute files; be sure they all
# have the same date.
latest_cat = '0000-00-00'
latest_req = '0000-00-00'
latest_att = '0000-00-00'
for file in all_files:
  mdate = date.fromtimestamp(os.lstat(file).st_mtime).strftime('%Y-%m-%d')
  if re.search('catalog_np', file, re.I) and mdate > latest_cat:
    latest_cat = mdate
    cat_file = file
  if re.search('requisites_np', file, re.I) and mdate > latest_req:
    latest_req = mdate
    req_file = file
  if re.search('attributes_np', file, re.I) and mdate > latest_att:
    latest_att = mdate
    att_file = file
if not ((latest_cat != '0000-00-00') and (latest_cat == latest_req) and (latest_req == latest_att)):
  print('*** FILE DATES DO NOT MATCH ***')
  for d, file in [[latest_att, att_file], [latest_cat, cat_file], [latest_req, req_file]]:
    print('  {} {}'.format(date.fromtimestamp(os.lstat(file).st_mtime).strftime('%Y-%m-%d'), file))
    exit()
if args.debug: print(latest_cat)

# Update the attributes table for all colleges
db.execute("delete from course_attributes")
with open(att_file, newline='') as csvfile:
  att_reader = csv.reader(csvfile)
  cols = None
  for row in att_reader:
    if cols == None:
      row[0] = row[0].replace('\ufeff', '')
      if 'Institution' == row[0]:
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
    else:
      q = ("insert into course_attributes values ('{}', '{}', '{}', '{}')".format(
          row[cols.index('course_id')],
          row[cols.index('institution')],
          row[cols.index('course_attribute')],
          row[cols.index('course_attribute_value')]))
      db.execute(q)
db.commit()

# Build dictionary of course requisites; key is (institution, discipline, course_number)
with open(req_file, newline='') as csvfile:
  req_reader = csv.reader(csvfile)
  requisites = {}
  cols = None
  for row in req_reader:
    if cols == None:
      row[0] = row[0].replace('\ufeff', '')
      if 'Institution' == row[0]:
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
    else:
      # discipline and course number are called subject and catalog
      value = row[cols.index('descr_of_pre_co-requisites')].strip()
      if value != '':
        key = (row[cols.index('institution')],
               row[cols.index('subject')],
               row[cols.index('catalog')])
        requisites[key] = value
if args.debug: print(len(requisites, 'requisites'))

# The query files are all ordered by institution, so courses can be processed sequentially
db.execute('delete from courses')
with open(cat_file, newline='') as csvfile:
  cat_reader = csv.reader(csvfile)
  cols = None
  for row in cat_reader:
    if cols == None:
      row[0] = row[0].replace('\ufeff', '')
      if 'Institution' == row[0]:
        cols = [val.lower().replace(' ', '_').replace('/', '_') for val in row]
    else:
      # Skip inactive and administrative courses; insert others
      #   2017-04-12: Retain inactive courses
      if row[cols.index('approved')] == 'A' and \
         row[cols.index('schedule_course')] == 'Y':
        course_id = row[cols.index('course_id')]
        college = row[cols.index('institution')]
        cuny_subject = row[cols.index('subject_external_area')]
        discipline = row[cols.index('subject')]
        number = row[cols.index('catalog_number')]
        title = row[cols.index('long_course_title')].replace("'", "’")
        catalog_component = row[cols.index('catalog_course_component')]
        hours = row[cols.index('contact_hours')]
        credits = row[cols.index('progress_units')]
        designation = row[cols.index('designation')]
        requisite_str = 'None'
        if (college, discipline, number) in requisites.keys():
          requisite_str = requisites[(college, discipline, number)].replace("'", "’")
        description = row[cols.index('descr')].replace("'", "’")
        career = row[cols.index('career')]
        status = row[cols.index('crse_catalog_status')]
        q = """
          insert or ignore into courses values(
          {}, '{}', '{}', '{}', '{}', '{}', '{:0.1f}',
          '{:0.1f}', '{}', '{}', '{}', '{}', '{}')""".format(
          course_id,
          college,
          cuny_subject,
          discipline,
          number,
          title,
          float(hours),
          float(credits),
          requisite_str,
          designation,
          description,
          career,
          status)
        db.execute(q)

db.execute("update institutions set date_updated='{}'".format(latest_cat))
db.commit()

