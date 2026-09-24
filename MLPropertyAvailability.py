# ------------------------ Property Manager by Mark Lasal - ML - --------------------------------------------
#                                   MLPropertyManager 
# PreRequirements:  - GoogleSheets where are tracked all the historical bookings, past and future
#                   - "Structures": python list of Structures to manage. Each Structure is described (name, spreadsheet name, ... ) as a python dictionary  
# 
# Solution : 
#   It loads the booking data from Google spreadsheets to a DWH featured by :-) sqlite3 relational database in memory.
#   On this database are executed SQL in order to have interesting  insights as:
#       - Summary key metrics cross structures and by structure
#       - Top 5 most profitable stays / bookings and bottom 5 least profitable ones
#       - Top 5 most profitable months and bottom 5 least profitable ones
#       ....
#
#   The user interaction and presentation is designed on streamlit
#   The target deploy is on streamlit cloud


import streamlit as st
import sqlite3
import gspread
import pandas as pd

import calendar
import datetime

def adapt_date_iso(val):
    """Adapt datetime.date to ISO 8601 date."""
    return val.isoformat()

def adapt_datetime_iso(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.replace(tzinfo=None).isoformat()

def adapt_datetime_epoch(val):
    """Adapt datetime.datetime to Unix timestamp."""
    return int(val.timestamp())

sqlite3.register_adapter(datetime.date, adapt_date_iso)
sqlite3.register_adapter(datetime.datetime, adapt_datetime_iso)
sqlite3.register_adapter(datetime.datetime, adapt_datetime_epoch)

def convert_date(val):
    """Convert ISO 8601 date to datetime.date object."""
    return datetime.date.fromisoformat(val.decode())

def convert_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.datetime.fromisoformat(val.decode())

def convert_timestamp(val):
    """Convert Unix epoch timestamp to datetime.datetime object."""
    return datetime.datetime.fromtimestamp(int(val))

sqlite3.register_converter("date", convert_date)
sqlite3.register_converter("datetime", convert_datetime)
sqlite3.register_converter("timestamp", convert_timestamp)

if "LoggedIn" not in st.session_state:
    st.session_state.LoggedIn = 0 

if "Run" not in st.session_state:
    st.session_state.Run = 0
else:
    st.session_state.Run += 1

if "Year" not in st.session_state:
    st.session_state.Year = 2026
  
# 1. Initialize a trigger to force the data refresh
if 'data_refresh_timestamp' not in st.session_state:
    st.session_state.data_refresh_timestamp = datetime.datetime.now()

print('')    
print('')    
print('')    
print('')    
print('----------------------------------------------------> SESSIOM RUN number:', st.session_state.Run)
print('----------------------------------------------------> IS THE STARTUP PHASE COMPLETED?:', st.session_state.LoggedIn)



st.set_page_config(page_title="ML Property Manager", layout="centered")
st.header("ML Property Manager 1.0")

#=============================================================================================================================
# For every managed strucure Read the data contained in the related Google Spreadsheet 
# The data are kept in memory (good choice?) in the "Data" item of the dictionary Structures[i] 
@st.cache_data
def ReadGSheets(trigger):
    print('----------------------------------------------------> ReadGSheets Run number:', st.session_state.Run)

    #gs_connection = gspread.service_account(filename = service_account_file)
    # st.secrets["gcp_service_account"] is a dictionary containing my google sheet service account credentals
    credentials_dict = st.secrets["gcp_service_account"] 
    # Authentication using directly the dictionary
    gs_connection = gspread.service_account_from_dict(credentials_dict)


    Structures = [  {'Ordinal': 1, 'Structure':'Dalla Nonna', 'StructureAddress':'Via ARMENISE 7',     'GoogleSheetName': 'Dalla Nonna Agenda 2025', 'From Date': '2025-05-31', 'Initial Investment': 150000.00},
                    {'Ordinal': 2, 'Structure':'La Cecchina', 'StructureAddress':'Via POSTIGLIONE 14b', 'GoogleSheetName': 'La Cecchina Agenda 2025', 'From Date': '2025-08-01', 'Initial Investment': 150000.00} 
                ]
    for structure in Structures:
        # Open a sheet from a spreadsheet in one go
        spreadsheet = gs_connection.open(structure['GoogleSheetName'])
        worksheet = spreadsheet.get_worksheet(0)
        Structures[structure['Ordinal'] - 1 ]['Data'] = worksheet.get_all_records()
        Structures[structure['Ordinal'] - 1 ]['Common Costs by Year'] = worksheet.get('common_costs_by_year')
   
        # print(structure['Structure'] + '\'s data extracted from ' + structure['GoogleSheetName'] + ' SpreadSheet')
        # st.write(structure['Structure'] + '\'s data extracted from ' + structure['GoogleSheetName'] + ' SpreadSheet')
 
    # In the new version of gspred library the session attribute has neen removed: the network resources are automalically deallocated 
    # gs_connection.session.close()
    return Structures

#=============================================================================================================================
@st.cache_resource
def get_db_connection(trigger):
    """Create the connection to the DB in memory. 
    It's decorated as <cache_resource>: 
    It's executed only one time and the connection object is stateful - ie it's alive during the user web session - ."""

    print('----------------------------------------------------> get_db_connection Run number:', st.session_state.Run)
    conn = sqlite3.connect(':memory:', check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    return conn

#=============================================================================================================================
# The data just read from the Google Sheets are mirrored to in-memory SQL tables using sqlite3.
def LoadTablesFromSheets(connection, Structures):
    print('----------------------------------------------------> LoadTablesFromSheets Run number:', st.session_state.Run)

    cursor = connection.cursor()

    for structure in Structures:
        data = structure['Data'] 
        if data:
            # 1. The table is dinamically created as: 
            # - Table name is GoogleSheetName
            # - Column names are the Structures[i].keys - ie the titles of the columns of the related sheet -
            # - Column type is text - ie the value in the sheet as is -
            # - Column <SheetRow> added as first column
            table_name = structure['GoogleSheetName']
            columns = data[0].keys()
            columns_str = 'SheetRow INTEGER PRIMARY KEY, ' + ', '.join(f'"{col}" TEXT' for col in columns)
            drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
            create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_str})'
            drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
            cursor.execute(drop_table_sql)
            cursor.execute(create_table_sql)
            #print(f'Table "{table_name}" successfully created in memory.')
    
            # 2. Load the sheet's data in the dedicated tab
            # Build the template for the SQL INSERT with the placeholder (?)
            placeholders = '?, ' + ', '.join(['?'] * len(columns))
            insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
    
            # For each row in the dictionary, manage the dictionary's values in the <values> list and execute the INSERT
            SheetRow = 1
            for row_dict in data:
                values = [row_dict[col] for col in columns]
                SheetRow += 1
                values.insert(0, SheetRow) 
                cursor.execute(insert_sql, values)
            #print(f'Table "{table_name}" successfully loaded.')
    
            # Commit all the changes
            connection.commit()
        else:
            print(print('----------------------------------------------------> ERROR LoadTablesFromSheets Run number:', st.session_state.Run))

#=============================================================================================================================
# Data cleaning before to load tha data into the datawarehouse
def CleaningData(connection, Structures):
    print('----------------------------------------------------> CleaningData Run number:', st.session_state.Run)

    cursor = connection.cursor()

    select = ''
    for structure in Structures:
        table_name = structure['GoogleSheetName']
        structure_name = structure['Structure']
        if structure['Ordinal'] > 1:
            select = select + ' UNION ALL '
        select = select + f'SELECT "{structure_name}" AS StructureName, "{table_name}" AS GoogleSheet, * FROM "{table_name}"' 
    select = select + ' ORDER BY 1, 2, 3 LIMIT 5'

    # for row in cursor.execute(select):
        # # 1. check the type consistency

        # # 2. check business rules

        # print(row)

    #3. Check for not overlapping periods and for "gap" periods (time window conseecutivity)
    print('---------- CHECK for any Gap or Overlapping periods in the booking rows -----------------------')
    #st.write('---------- CHECK for any Gap or Overlapping periods in the booking rows -----------------------')
    for structure in Structures:
        table_name = structure['GoogleSheetName']
        structure_name = structure['Structure']
        select = f'''
        WITH raw_bookings (StructureName, SheetRow, FromDate, ToDate, NextFromDate, Rank) AS 
        ( 
        SELECT 
            "{structure_name}"  AS StructureName
            , SheetRow          AS SheetRow
            , "From Date"       AS FromDate
            , "To Date"         AS ToDate 
            , LEAD("From Date", 1) OVER (PARTITION BY "{structure_name}" ORDER BY "From Date" ) AS NextFromDate
            , DENSE_RANK() OVER (PARTITION BY "{structure_name}" ORDER BY "From Date" ) AS Rank 
        FROM "{table_name}"
        )
        SELECT
            StructureName, SheetRow, FromDate, ToDate, NextFromDate
        FROM raw_bookings    
        WHERE ToDate <> NextFromDate   --> the last row has null value in NextFromDate, but it's not extracted because the expression (value <> null) returns "Unknown" and not  "True"  
        ORDER BY StructureName, FromDate
        '''
        cursor.execute(select)
        rows = cursor.fetchall()
        if not rows:
            print(f'The booking\'s dates are well set in the "{table_name}" sheet for the "{structure_name}" strucuture')
            #st.write(f'The booking\'s dates are well set in the "{table_name}" sheet for the "{structure_name}" strucuture')
        else:
            # Nice To Have: 
            # not report the rows with error but fix them with correct ToDate value
            # How: using the CTE above, change the final SELECT in an UPDATE the column ToDate =  NextFromDate only for the rows with error
            for row in rows:
                #print(f'"{structure_name}": in the row {row[1]} of the sheet "{table_name}" the booking has {row[3]} as last date that is not contiguous with next booking\'s  start date')
                #st.write('---------- CHECK for any Gap or Overlapping periods in the booking rows -----------------------')
                st.write(f'"{structure_name}": in the row {row[1]} of the sheet "{table_name}" the booking has {row[3]} as last date that is not contiguous with next booking\'s  start date')

#===========================================================================================================================#
#===========================================================================================================================#
#															                                                                #
#												====================                                                        #
#					                            DATAWAREHOUSE SCHEMA								                        #
#					                            ====================								                        #
#															                                                                #
#		______________		    ________________________			                ____________		                    #
#		| structures | -------> | common_costs_by_year |			                | calendar |		                    #
#		--------------		    ------------------------			                ------------		                    #
#		      |										                                      |			                        #
#		      |										                                      |			                        #
#		      |			        ____________		    ___________________               |			                        #
#		      |---------------> | bookings | --------->	| bookings_by_day | <-------------			                        #
#					            ------------		    -------------------					                                #
#															                                                                #
#===========================================================================================================================#
#===========================================================================================================================#
# Create and Load the DWH (datawarehouse) tables

def LoadDWH(connection, Structures):
    print('----------------------------------------------------> LoadDWH Run number:', st.session_state.Run)
    
    cursor = connection.cursor()
    
# 1. Create "bookings" table"
    table_name = 'bookings'

    drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
    cursor.execute(drop_table_sql)

    columns = [
    'StructureName TEXT',
    'FromDate DATE',
    'ToDate DATE',
    'Channel TEXT',
    'Nights INTEGER',
    'Guests INTEGER',
    'Status TEXT',
    'GuestAmountPaid REAL',
    'Tax REAL',
    'HostEarnings REAL',
    'PlatformEarnings REAL',
    'TouristTax REAL',
    'TaxPaidFlag BOOLEAN',
    'CleaningCost REAL',
    'LaundryCost REAL',
    'Note TEXT'
    ]
    columns_str = 'booking_id INTEGER PRIMARY KEY, ' + ', '.join(f'{col}' for col in columns)
    create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_str})'
    cursor.execute(create_table_sql)
    print(f'Table "{table_name}" successfully created in memory.')
    #st.write(f'Table "{table_name}" successfully created in memory.')

# 1.a load "bookings" table from every table defined in the "Structures" dictionary
#     Only the real booked are loaded (Status <> 'Free') and not the free slots - not booked or not still booked time windows -
    insert_into = f'''
    INSERT INTO {table_name} (
    StructureName, FromDate, ToDate, Channel, Nights, Guests, Status, GuestAmountPaid, Tax, HostEarnings, PlatformEarnings, TouristTax, TaxPaidFlag, CleaningCost, LaundryCost, Note)
    '''
    select = ''
    for structure in Structures:
        structure_name = structure['Structure']
        table_name = structure['GoogleSheetName']
        if structure['Ordinal'] > 1:
            select = select + ' UNION ALL '
        select = select + f'''
        SELECT 
            "{structure_name}" AS StructureName
            ,DATE("From Date")  AS FromDate
            ,DATE("To Date") AS ToDate
            ,"Channel"AS Channel
            ,CAST("Nights" AS INTEGER) AS Nights
            ,CAST("Guests" AS INTEGER) AS Guests
            ,"Status" AS Status
            ,CAST(REPLACE(REPLACE("Amount Paid",'€',''), ',','') AS REAL) AS GuestAmountPaid
            ,CAST(REPLACE(REPLACE("Flat-rate Tax 21%",'€',''), ',','') AS REAL)  AS Tax
            ,CAST(REPLACE(REPLACE("Host Earnings",'€',''), ',','') AS REAL)  AS HostEarnings
            ,CAST(REPLACE(REPLACE("Platform Earnings",'€',''), ',','') AS REAL)  AS PlatformEarnings
            ,CAST(REPLACE(REPLACE("Tourist Tax",'€',''), ',','') AS REAL)  AS TouristTax
            ,CAST((CASE WHEN "Tourist Tax Paid" IN ('Pagata a Papà', 'Pagata a Cesare') THEN 1 ELSE 0 END) AS BOOLEAN) AS TaxPaidFlag
            ,CAST(REPLACE(REPLACE("Cleaning Fee",'€',''), ',','') AS REAL)  AS CleaningCost
            ,CAST(REPLACE(REPLACE("Laundry Fee",'€',''), ',','') AS REAL)  AS LaundryCost
            ,"Note" AS Note
        FROM "{table_name}"
        WHERE LOWER("Status") <> 'free'
        ''' 
    select = select + ' ORDER BY StructureName, FromDate'

    cursor.execute(insert_into + ' ' + select)
    connection.commit()

    select = '''
             SELECT StructureName, COUNT(*), MIN(FromDate), MAX(ToDate), julianday(MAX(ToDate)) - julianday(MIN(FromDate)), SUM(Nights), SUM(GuestAmountPaid), SUM(Tax)
             FROM bookings 
             GROUP BY StructureName
             '''
    cursor.execute(select)
    rows = cursor.fetchall()
    if not rows:
        print(f'ERROR: NO ROWS LOADED IN THE <bookings> TABLE')
        #st.writeite(f'ERROR: NO ROWS LOADED IN THE <bookings> TABLE')
    else:
        for row in rows:
            print(f'Loaded {row[1]} rows (bookings) for {row[0]} structure')
            #st.write(f'Loaded {row[1]} rows (bookings) for {row[0]} structure')

#=============================================================================================================================
# 2. Create "bookings by day" table": Fact table containing revenue and cost metrics at a daily granularity.  
    table_name = 'bookings_by_day'
    drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
    cursor.execute(drop_table_sql)

    columns = [
      'Booking_id INTEGER'
    , 'Day DATE'
    , 'Check_IN BOOLEAN'
    , 'GuestAmountPaidByDay REAL'
    , 'TaxByDay REAL'
    , 'HostEarningsByDay REAL'
    , 'PlatformEarningsByDay REAL'
    , 'CleaningCostByDay REAL'
    , 'LaundryCostByDay REAL'
    , 'CommonCostByDay REAL'
    ]
    columns_str = 'booking_by_day_id INTEGER PRIMARY KEY, ' + ', '.join(f'{col}' for col in columns)
    create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_str})'
    cursor.execute(create_table_sql)
    #print(f'Table "{table_name}" successfully created in memory.')

# 2.a load "bookings by day" table generating rows for each row between bookings.FromDate and bookings.ToDate
    insert_into = f'''
    INSERT INTO {table_name} (
      Booking_id
    , Day
    , Check_IN
    , GuestAmountPaidByDay
    , TaxByDay
    , HostEarningsByDay
    , PlatformEarningsByDay
    , CleaningCostByDay
    , LaundryCostByDay
    , CommonCostByDay
    )
    '''

    select = '''
WITH RECURSIVE BookingByDay (booking_id, Day, FromDate, ToDate) AS (
SELECT booking_id AS booking_id, FromDate AS Day, FromDate AS FromDate, ToDate AS ToDate
FROM bookings
UNION ALL
SELECT BookingByDay.booking_id AS booking_id, DATE(BookingByDay.Day, '+1 day') AS Day, BookingByDay.FromDate AS FromDate, BookingByDay.ToDate AS ToDate
FROM bookings
INNER JOIN BookingByDay ON (bookings.booking_id = BookingByDay.booking_id AND DATE(BookingByDay.Day, '+1 day') < bookings.ToDate) 
)
SELECT
  bookings.Booking_id                                                     AS Booking_id
, BookingByDay.Day                                                        AS Day
, CASE WHEN BookingByDay.Day = bookings.FromDate THEN TRUE ELSE FALSE END AS Check_IN
, bookings.GuestAmountPaid / bookings.Nights                              AS GuestAmountPaidByDay
, bookings.Tax / bookings.Nights                                          AS TaxByDay
, bookings.HostEarnings / bookings.Nights                                 AS HostEarningsByDay
, bookings.PlatformEarnings / bookings.Nights                             AS PlatformEarningsByDay
, bookings.CleaningCost / bookings.Nights                                 AS CleaningCostByDay
, bookings.LaundryCost / bookings.Nights                                  AS LaundryCostByDay
, 0 AS CommonCostByDay
from BookingByDay
INNER JOIN bookings ON (BookingByDay.booking_id = bookings.booking_id)
order by bookings.booking_id, BookingByDay.Day
    '''

    cursor.execute(insert_into + ' ' + select)
    connection.commit()

    select = '''
SELECT bookings.StructureName, bookings.booking_id, MAX(bookings.Nights), COUNT(*), MAX(GuestAmountPaid), SUM(GuestAmountPaidByDay), MAX(HostEarnings), SUM(PlatformEarningsByDay)  
FROM bookings 
INNER JOIN bookings_by_day ON (bookings.booking_id = bookings_by_day.booking_id) 
GROUP BY bookings.StructureName, bookings.booking_id
LIMIT 10
    '''
    #for row in cursor.execute(select):
    #    print(row)

#=============================================================================================================================
# 3. Create the 'structures' table 
    table_name = 'structures'
    drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
    cursor.execute(drop_table_sql)

    # table defined without ID as Primary Key: this choice makes easier the queries on 'bookings' table and doesn't impact the perfomance ... :-) I hope  
    columns = [
'StructureName TEXT PRIMARY KEY',
'StructureAddress TEXT',
'AvailableFromDate DATE',
'AvailableToDate DATE',
'GoogleSheetName TEXT',
'InitialInvestment REAL',
'Ordinal INTEGER'
    ]
    columns_str = ', '.join(f'{col}' for col in columns)
    create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_str})'
    cursor.execute(create_table_sql)
    #print(f'Table "{table_name}" successfully created in memory.')

# 3.b Load the list of the structure dictionaries into 'structure's SQL Table
# Build the template for the SQL INSERT with the placeholder (?)
    table_name = 'structures'
    placeholders = ', '.join(['?'] * len(columns))
    insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
    for structure in Structures:
        select = f'SELECT DATE(MAX("To Date")) FROM "{structure['GoogleSheetName']}"'
        cursor.execute(select)
        row = cursor.fetchone()
        values = [structure['Structure'], structure['StructureAddress'], structure['From Date'], row[0], structure['GoogleSheetName'], structure['Initial Investment'], structure['Ordinal']]
        cursor.execute(insert_sql, values)
    #print(f'Table "{table_name}" successfully loaded.')
    
# Commit all the changes
    connection.commit()

#=============================================================================================================================
# 4. Create the 'common_costs_by_year' table 
    table_name = 'common_costs_by_year'
    drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
    cursor.execute(drop_table_sql)

    columns = [
  'StructureName TEXT'
, 'Year INTEGER'
, 'Months INTEGER'
, 'Days INTEGER'
, 'PropertyTax REAL'
, 'CondoFees REAL'  
, 'ElectricityCost REAL'
, 'GasCost REAL'
, 'WiFiCost REAL'
, 'MaintenanceMiscellaneousCost REAL'
, 'AmenitiesCost REAL'
, 'AvailableFromDate DATE'
, 'AvailableToDate DATE'
    ]

    columns_str = 'common_costs_by_year_id INTEGER PRIMARY KEY, ' + ', '.join(f'{col}' for col in columns)
    create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_str})'
    cursor.execute(create_table_sql)
    #print(f'Table "{table_name}" successfully created in memory.')


# 4.a Load the list of the structure dictionaries into structures SQL Table
# Build the template for the SQL INSERT with the placeholder (?)
    placeholders = ', '.join(['?'] * len(columns))
    insert_sql = f'''
        INSERT INTO "{table_name}" 
        (StructureName, Year, Months, Days, PropertyTax,  CondoFees,  ElectricityCost,  GasCost,  WiFiCost, MaintenanceMiscellaneousCost, AmenitiesCost, AvailableFromDate, AvailableToDate)
        VALUES ({placeholders})
    '''
    for structure in Structures:
        for row in structure['Common Costs by Year'] [1:]:
            # sheet row values:                   ['Year', 'Month', 'Days', 'Property Tax',                          'Condo Fees',                            'Electricity Cost',                      'Gas Cost',                              'Wi-Fi',                                 'Maintenance and Miscellaneous Cost',    'Amenities Cost',                       'From Date',         'To Date']
            # table columns:      'StructureName', 'Year', 'Months','Days', 'PropertyTax',                           'CondoFees',                             'ElectricityCost',                       'GasCost',                               'WiFiCost',                              'MaintenanceMiscellaneousCost',          'AmenitiesCost',                        'AvailableFromDate', 'AvailableToDate'
            values = [     structure['Structure'], row[0], row[1],  row[2], row[3].replace('€','',).replace(',',''), row[4].replace('€','',).replace(',',''), row[5].replace('€','',).replace(',',''), row[6].replace('€','',).replace(',',''), row[7].replace('€','',).replace(',',''), row[8].replace('€','',).replace(',',''), row[9].replace('€','',).replace(',',''), row[10],            row[11]   ]  
            cursor.execute(insert_sql, values)
    #print(f'Table "{table_name}" successfully loaded.')
    
# Commit all the changes
    connection.commit()

# Check
    cursor.execute("SELECT * FROM common_costs_by_year")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

#=============================================================================================================================
# 5. 'Calendar' table: useful for insights by monthly and/or season 
    table_name = 'calendar'
    drop_table_sql = f'DROP TABLE IF EXISTS "{table_name}"'
    cursor.execute(drop_table_sql)

    cursor.execute(f'''
    CREATE TABLE "{table_name}" (
        id INTEGER PRIMARY KEY,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        first_day_of_month TEXT NOT NULL,
        last_day_of_month TEXT NOT NULL,
        season TEXT NOT NULL
    );
    ''')

    # How long ?
    start_year = 2025
    end_year = 2027

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            # First and last day in the month
            first_day = datetime.date(year, month, 1)
            # calendar.monthrange(year, month) -> number of days in the month
            last_day_num = calendar.monthrange(year, month)[1]
            last_day = datetime.date(year, month, last_day_num)

            # Season: the season id the the first day of month and not the 21st
            if month in [12, 1, 2]:
                season = 'winter'
            elif month in [3, 4, 5]:
                season = 'spring'
            elif month in [6, 7, 8]:
                season = 'summer'
            else: # month in [9, 10, 11]
                season = 'fall / autumn'
        
            cursor.execute('''
                INSERT INTO Calendar (year, month, first_day_of_month, last_day_of_month, season)
                VALUES (?, ?, ?, ?, ?);
                ''', (year, month, first_day, last_day, season))

    connection.commit()

    # Check
    #cursor.execute("SELECT 'Months: ', COUNT(*), 'from: ', MIN(first_day_of_month), MIN(last_day_of_month), 'To: ', MAX(first_day_of_month), MAX(last_day_of_month) FROM Calendar")
    #row = cursor.fetchone()
    #if row:
    #    print(row)


#=============================================================================================================================
# High level insights 
def HighLevelInsights():  

    print('----------------------------------------------------> HighLevelInsights Run number:', st.session_state.Run)

    connection =  get_db_connection(st.session_state.data_refresh_timestamp)
    cursor = connection.cursor()
    year = st.session_state.Year

    select = f"""
SELECT 
    COUNT(DISTINCT(bookings_by_day.booking_by_day_id))                                                                          AS BookedNights
    ,(SELECT SUM(common_costs_by_year.Days) FROM common_costs_by_year WHERE common_costs_by_year.Year = {year})                 AS AvailableNights
    ,SUM(bookings_by_day.HostEarningsByDay)                                                                                     AS TotalRevenue
    ,(SELECT SUM(PropertyTax + CondoFees + ElectricityCost + GasCost + WiFiCost + MaintenanceMiscellaneousCost + AmenitiesCost) FROM common_costs_by_year WHERE Year = {year}) 
                                                                                                                                AS TotalCommonCost
    ,(SUM(bookings_by_day.CleaningCostByDay) + SUM(bookings_by_day.LaundryCostByDay))                                           AS CleaningCost
    ,COUNT(DISTINCT(bookings_by_day.booking_id))                                                                                AS StayCount
    ,(SELECT SUM(MaintenanceMiscellaneousCost) FROM common_costs_by_year WHERE Year = {year})                                   AS MaintFurnishCost
    ,(SELECT COUNT(*) from structures)                                                                                          AS StructureCount
    ,(SELECT GROUP_CONCAT(StructureName, ', ') from structures ORDER BY Ordinal)                                                AS StructureNamesList
    ,(SELECT AVG(InitialInvestment) from structures)                                                                             AS AverageIntialInvestment
                 
FROM bookings_by_day
WHERE strftime('%Y', Day) = '{year}'
    """

    
    cursor.execute(select)
    row = cursor.fetchone()
    if row:
        structure_count = row[7]
        structure_names_list = row[8]

        booked_nights = row[0]
        available_nights = row[1]
        occupancy_rate =  booked_nights / available_nights * 100
        number_of_stays = row[5]

        revenue = row[2]
        cleaning_cost = row[4]
        net_revenue = revenue - cleaning_cost

        common_cost = row[3]
        maint_furnish_cost = row[6]
        net_profit = net_revenue - common_cost

        estimated_full_year_profit = net_profit * 364 / available_nights # the big assumption is to keep for all the year the same occupancy rate and revenue, on average  
        estimated_full_month_profit = estimated_full_year_profit / 12

        average_intial_investment = row[9]




        daily_revenue = revenue / booked_nights
        daily_net_profit = net_profit / booked_nights
        yearly_booked_nights = occupancy_rate * 364 / 100
        yearly_net_profit = yearly_booked_nights * daily_net_profit
        monthly_net_profit = yearly_net_profit / 12


        yearly_net_profit1 = net_profit * 364 / available_nights
        monthly_net_profit1 = yearly_net_profit1 / 12


        st.write(f"""
                 The following insights are based on  ***{year}*** booking data and actual costs to date, plus projections through December 31st.
                 """)
        st.write(f""" 
                 The managed structures are {structure_count} : *{structure_names_list}*
                 """)
        st.divider()
#
#       1st Insight: here a sort of simplified Profit and Loss (P&L) Statement:
#
        st.markdown(f"""
                 ###### Very simply, which are the Profit and Loss (P&L) Statement? 
                 """)
        with st.expander(f"**On average, the *estimated* monthly net profit is €{estimated_full_month_profit:.2f} per apartment.**"
                         , expanded = True):
            st.markdown(f"""
                     Nights sold : {booked_nights} on {available_nights} nights (Rate of {occupancy_rate:.1f}%)<br>
                     Revenue     : {revenue:.2f} € (after commis. & taxes)<br>
                     Cleaning Cost: {cleaning_cost:.2f} € (for {number_of_stays} stays)<br>
                     Net Revenue: {net_revenue:.2f} € (after clean & laundry)<br>
                     Common Cost: {common_cost:.2f} € (Mainten.: {maint_furnish_cost:.2f}€)<br>
                     Net Profit: {net_profit:.2f} € (Bottom Line Profit)<br>


                     #### Estimated Full Year Profit per Structure: {estimated_full_year_profit:.2f} €
                     The strong assumption is that the average occupancy rate and revenue will remain constant throughout the year

                     """,
                     unsafe_allow_html = True)
        st.divider()
#
#       2nd Insight: Can this job - i.e. property management - replace an average employment's salary?
#
        target_yeraly_profit = 40000
        st.markdown(f"""
                 ###### Can this job - i.e. property management - replace an average employment's salary? 
                 """)
        with st.expander(f"""**To achieve a net annual profit of {target_yeraly_profit / 1000:.1f} K€ - managerial annual net salary - you have  
                         to manage {target_yeraly_profit/estimated_full_year_profit:.1f} flats as like as {structure_names_list}.
                         To reach the goal you have to buy and set-up other {target_yeraly_profit/estimated_full_year_profit - structure_count:.1f} 
                         units with an *estimated* investment of about {(target_yeraly_profit/estimated_full_year_profit - structure_count) * average_intial_investment / 1000:.1f} K€.**"""
                         , expanded = False):
            st.markdown(f"""
                     1.0 Flats ==> net {estimated_full_year_profit / 1000 :.1f} K€ per year<br>
                     {target_yeraly_profit/estimated_full_year_profit:.1f} Flats ==> net {target_yeraly_profit / 1000 :.1f} K€ per year<br>
                     <br>
                     GIVEN THAT miss {target_yeraly_profit/estimated_full_year_profit - structure_count:.1f} flats<br>
                     <br>
                     {average_intial_investment / 1000 :.1f} K€ ==> to buy and setup 1 Flat<br>
                     {(target_yeraly_profit/estimated_full_year_profit - structure_count) * average_intial_investment / 1000:.1f} K€ ==> to buy and setup {target_yeraly_profit/estimated_full_year_profit - structure_count:.1f} Flat<br>


                     ##### Additional estimated investment for a managerial annual salary: {(target_yeraly_profit/estimated_full_year_profit - structure_count) * average_intial_investment / 1000:.1f} K€
                     """,
                     unsafe_allow_html = True)
        st.divider()
#
#       3rd Insight: Is this investment and related job (buying flats in my city like "LA Cecchina", ... and managing them) profitable?
#
        net_historical_equity_return_rate = 8 # 8%
        net_avg_italian_govt_bond_yield = 2.75 # 3% 
        my_NetRentalYield = estimated_full_year_profit / average_intial_investment * 100
        st.markdown(f"""
                 ###### Do you suggest to buy a flat and manage it as like as {structure_names_list}? 
                 """)
        with st.expander(f"**On average, the estimated yearly Net Rental Yield (NRY) - coming from my properties - is {my_NetRentalYield:.2f}%.**"
                         , expanded = False):
            st.markdown(f"""
                     Inital Capital: {average_intial_investment / 1000:.1f} K€ (for a flat like mine)<br>  

                     **Global Equity Benchmark: {net_historical_equity_return_rate:.2f}%**<br> 
                     Annual Return:  {net_historical_equity_return_rate / 100 * average_intial_investment / 1000:.2f}K€<br> 
                     (--High Risk --not Annual Revenue/Cash ++Capital Appreciation but after years)<br>

                     **Italian Government Bond: {net_avg_italian_govt_bond_yield:.2f}%**<br>
                     Annual Revenue: {net_avg_italian_govt_bond_yield / 100 * average_intial_investment / 1000:.2f}K€(Bond Coupons/Cedole)<br>
                     (++Low Risk ++low Annual Revenue/Cash --Inflation-devalued capital)<br>

                     **My yearly Net Rental Yield (NRY): {my_NetRentalYield:.2f}%**<br>
                     **Annual Net Profit: {my_NetRentalYield / 100 * average_intial_investment / 1000:.2f}K€**<br>
                     **(++Low Risk ++good Annual Revenue/Cash ++ Capital Appreciation**<br>
                     
                     Far less risky than stocks, but {my_NetRentalYield / net_avg_italian_govt_bond_yield :.2f} times more profitable than Italian government bonds, while simultaneously preserving the initial capital from inflation over time.
                     
                     """,
                     unsafe_allow_html = True)
 


        st.divider()
            
    else:
        #print('Error: /n' + select)
        st.write('Error in: /n' + select)

#=============================================================================================================================
def ProfitLostByStructure():

    print('----------------------------------------------------> ProfitLostByStructure Run number:', st.session_state.Run)

    connection =  get_db_connection(st.session_state.data_refresh_timestamp)
    cursor = connection.cursor()
    year = st.session_state.Year


    select = f"""
 SELECT 
     MAX('0. Total Nights Sold:')                                                                                           AS Metric
     ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN 1 ELSE 0 END)                                               AS La_Cecchina        
     ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN 1 ELSE 0 END)                                               AS Dalla_Nonna        
 FROM bookings_by_day
 INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
 WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

 UNION ALL

SELECT 
    MAX('1. Gross Revenue:')                                                                                                AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.GuestAmountPaidByDay ELSE 0 END)             AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.GuestAmountPaidByDay ELSE 0 END)             AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('1.a Brokerage Fees:')                                                                                              AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.PlatformEarningsByDay ELSE 0 END)            AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.PlatformEarningsByDay ELSE 0 END)            AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('1.b Taxes:')                                                                                                       AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.TaxByDay ELSE 0 END)                         AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.TaxByDay ELSE 0 END)                         AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('2. Revenue after Tax&Commiss.:')                                                                                   AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.HostEarningsByDay ELSE 0 END)                AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.HostEarningsByDay ELSE 0 END)                AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('2.a Cleaning Cost:')                                                                                               AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.CleaningCostByDay ELSE 0 END)                AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.CleaningCostByDay ELSE 0 END)                AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('2.b Laundry Cost:')                                                                                               AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.LaundryCostByDay ELSE 0 END)                AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.LaundryCostByDay ELSE 0 END)                AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('3. NET Revenue:')                                                                                                     AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' 
                THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay 
                ELSE 0 
        END)                                                                                                               AS La_Cecchina        
    ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' 
                THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay
                ELSE 0
        END)                                                                                                               AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('3.a1 ===== Patrimonial Tax:')                                                                                           AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.PropertyTax ELSE 0 END)   AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.PropertyTax ELSE 0 END)   AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.a2 ===== Maintenance Cost:')                                                                                          AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.MaintenanceMiscellaneousCost ELSE 0 END)    AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.MaintenanceMiscellaneousCost ELSE 0 END)    AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.a Ownership Cost:')                                                                                          AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.PropertyTax + common_costs_by_year.MaintenanceMiscellaneousCost ELSE 0 END)    AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.PropertyTax + common_costs_by_year.MaintenanceMiscellaneousCost ELSE 0 END)    AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.b1 ===== Condo cost:')                                                                                           AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.CondoFees ELSE 0 END)   AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.CondoFees ELSE 0 END)   AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.b2 ===== Electricity Cost:')                                                                                           AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.ElectricityCost ELSE 0 END)   AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.ElectricityCost ELSE 0 END)   AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.b3 ===== Gas Cost:')                                                                                           AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.GasCost ELSE 0 END)   AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.GasCost ELSE 0 END)   AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.b4 ===== Wi-Fi Cost:')                                                                                           AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.WiFiCost ELSE 0 END)   AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.WiFiCost ELSE 0 END)   AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('3.b5 ===== Amenities Cost:')                                                                                           AS Metric
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN  common_costs_by_year.AmenitiesCost ELSE 0 END)   AS La_Cecchina
    ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN  common_costs_by_year.AmenitiesCost ELSE 0 END)   AS Dalla_Nonna
FROM common_costs_by_year
WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
     MAX('3.b Operational Cost:')                                                                                     AS Metric
     ,MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN 
               common_costs_by_year.CondoFees + common_costs_by_year.ElectricityCost + common_costs_by_year.GasCost + WiFiCost + AmenitiesCost
          ELSE 0 END)                                                                                                            AS La_Cecchina
     ,MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN
               common_costs_by_year.CondoFees + common_costs_by_year.ElectricityCost + common_costs_by_year.GasCost + WiFiCost + AmenitiesCost
          ELSE 0 END)                                                                                                            AS La_Cecchina
 FROM common_costs_by_year
 WHERE common_costs_by_year.Year ={year}

UNION ALL

SELECT 
    MAX('4. Profit & Loss:')                                                                                   AS Metric
    ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' 
                THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay 
                ELSE 0 
         END)
     -
     MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN   common_costs_by_year.PropertyTax + common_costs_by_year.CondoFees 
                 + common_costs_by_year.ElectricityCost + common_costs_by_year.GasCost + WiFiCost + MaintenanceMiscellaneousCost + AmenitiesCost
          ELSE 0 END)                                                                                                            AS La_Cecchina
     ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' 
                 THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay
                 ELSE 0
         END)
     -
     MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN   common_costs_by_year.PropertyTax + common_costs_by_year.CondoFees 
                 + common_costs_by_year.ElectricityCost + common_costs_by_year.GasCost + WiFiCost + MaintenanceMiscellaneousCost + AmenitiesCost
          ELSE 0 END)                                                                                                            AS La_Cecchina
 FROM bookings_by_day
 INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
 INNER JOIN common_costs_by_year ON (common_costs_by_year.StructureName = bookings.StructureName AND common_costs_by_year.Year ={year})
 WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

ORDER BY Metric
    """
    dataframe = pd.read_sql(select, connection)
    st.dataframe(dataframe)


def SoldNightFigures():

    print('----------------------------------------------------> SoldNightFigures Run number:', st.session_state.Run)

    connection =  get_db_connection(st.session_state.data_refresh_timestamp)
    cursor = connection.cursor()
    year = st.session_state.Year


    select = f"""
 SELECT 
     MAX('0. Total Nights Sold:')                                                                                           AS Metric
     ,SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN 1 ELSE 0 END)                                               AS La_Cecchina        
     ,SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN 1 ELSE 0 END)                                               AS Dalla_Nonna        
 FROM bookings_by_day
 INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
 WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

 UNION ALL

 SELECT 
     MAX('1. occupancy %:')                                                                                                      AS Metric
     ,ROUND(
     CAST(SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN 1 ELSE 0 END) AS REAL)                                                    
     / MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN common_costs_by_year.Days ELSE 0 END)               
     * 100, 2)                                                                                                                   AS La_Cecchina        
     ,ROUND(
     CAST(SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN 1 ELSE 0 END) AS REAL)                                                    
     / MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN common_costs_by_year.Days ELSE 0 END)               
     *100, 2)                                                                                                                    AS Dalla_Nonna        
 FROM bookings_by_day
 INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
 INNER JOIN common_costs_by_year ON (common_costs_by_year.StructureName = bookings.StructureName AND common_costs_by_year.Year ={year})
 WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('2. Paid by Guest per Day:')                                                                                            AS Metric
    ,ROUND(
    CAST(SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN bookings_by_day.GuestAmountPaidByDay ELSE 0 END) AS REAL)   
    / SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN 1 ELSE 0 END) 
    , 2)                                                                                                                        AS La_Cecchina        
    ,ROUND(
    CAST(SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN bookings_by_day.GuestAmountPaidByDay ELSE 0 END) AS REAL)   
    / SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN 1 ELSE 0 END) 
    , 2)                                                                                                                        AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

UNION ALL

SELECT 
    MAX('3. NET Revenue per Booked Day:')                                                                                                  AS Metric
    ,ROUND(
    CAST(SUM(CASE WHEN bookings.StructureName = 'La Cecchina' 
                THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay 
                ELSE 0 
        END) AS REAL)
    / SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN 1 ELSE 0 END)
    , 2)                                                                                                                         AS La_Cecchina        
    ,ROUND(
    CAST(SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' 
                THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay
                ELSE 0
        END) AS REAL)
    / SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN 1 ELSE 0 END)               
    , 2)                                                                                                                        AS Dalla_Nonna        
FROM bookings_by_day
INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
INNER JOIN common_costs_by_year ON (common_costs_by_year.StructureName = bookings.StructureName AND common_costs_by_year.Year ={year})
WHERE strftime('%Y', bookings_by_day.Day) = '{year}'


UNION ALL 


 SELECT 
     MAX('4. Profit x Booked Day:')                                                                                              AS Metric
     ,ROUND(
     CAST((SUM(CASE WHEN bookings.StructureName = 'La Cecchina' 
                 THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay 
                 ELSE 0 
         END)
     -
     MAX(CASE WHEN common_costs_by_year.StructureName = 'La Cecchina' THEN   common_costs_by_year.PropertyTax + common_costs_by_year.CondoFees 
                 + common_costs_by_year.ElectricityCost + common_costs_by_year.GasCost + WiFiCost + MaintenanceMiscellaneousCost + AmenitiesCost
          ELSE 0 END)) AS REAL)                                                                                                           
      / SUM(CASE WHEN bookings.StructureName = 'La Cecchina' THEN 1 ELSE 0 END) 
     , 2)                                                                                                                        AS La_Cecchina
     ,ROUND(
     CAST((SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' 
                 THEN bookings_by_day.HostEarningsByDay - bookings_by_day.CleaningCostByDay - bookings_by_day.LaundryCostByDay
                 ELSE 0
         END) 
     -
     MAX(CASE WHEN common_costs_by_year.StructureName = 'Dalla Nonna' THEN   common_costs_by_year.PropertyTax + common_costs_by_year.CondoFees 
                 + common_costs_by_year.ElectricityCost + common_costs_by_year.GasCost + WiFiCost + MaintenanceMiscellaneousCost + AmenitiesCost
          ELSE 0 END)) AS REAL)
     / SUM(CASE WHEN bookings.StructureName = 'Dalla Nonna' THEN 1 ELSE 0 END) 
     , 2)                                                                                                                        AS La_Cecchina
 FROM bookings_by_day
 INNER JOIN bookings ON(bookings.booking_id = bookings_by_day.booking_id)
INNER JOIN common_costs_by_year ON (common_costs_by_year.StructureName = bookings.StructureName AND common_costs_by_year.Year ={year})
 WHERE strftime('%Y', bookings_by_day.Day) = '{year}'

ORDER BY Metric
    """
    dataframe = pd.read_sql(select, connection)
    st.dataframe(dataframe)


def trigger_data_refresh():
    st.session_state.data_refresh_timestamp = datetime.datetime.now()

    Structures = ReadGSheets(st.session_state.data_refresh_timestamp)
    connection = get_db_connection(st.session_state.data_refresh_timestamp)
    LoadTablesFromSheets(connection, Structures)
    CleaningData(connection, Structures)
    LoadDWH(connection, Structures)


def DataRefresh():
    print('----------------------------------------------------> DataRefresh Run number:', st.session_state.Run)

    st.write(f"""
             The last data refresh occurred on {st.session_state.data_refresh_timestamp.strftime("%d/%m/%Y %H:%M:%S")}
             """)
    st.button("DATA REFRESH", on_click=trigger_data_refresh)


#=============================================================================================================================
#=============================================================================================================================
#=============================================================================================================================

Structures = ReadGSheets(st.session_state.data_refresh_timestamp)
connection = get_db_connection(st.session_state.data_refresh_timestamp)
if not st.session_state.LoggedIn:
    LoadTablesFromSheets(connection, Structures)
    CleaningData(connection, Structures)
    LoadDWH(connection, Structures)
    #st.write('The start-up is completed: the google sheet\'s data have been controlled and moved in the SQL database.')

    st.session_state.LoggedIn = 1  # Terminated the computation to do only in the login phase
    #st.write('Press the OK button to proceed')
    #if st.button("OK"):
    #    pass

year = st.session_state.Year
HighLevelInsights_page = st.Page(HighLevelInsights, title= str(year) + " Insights", icon="🏠")
ProfitLostByStructure_page = st.Page(ProfitLostByStructure, title= str(year) + " P&L by Structure", icon="📈")
SoldNightFigures_page = st.Page(SoldNightFigures, title= str(year) + " Sold Night Figures", icon="🌙")


DataRefresh_page = st.Page(DataRefresh, title= "Data Refresh", icon="🔄")



pg = st.navigation(
        {
            "Insights": [HighLevelInsights_page, ProfitLostByStructure_page, SoldNightFigures_page],
            "Settings": [DataRefresh_page],
        }
    )
pg.run()


                                          
print('----------------------------------------------------> This the last istruction Run number:', st.session_state.Run)








 
