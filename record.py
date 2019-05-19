import requests
import json
import time
import sys
import os

from google.protobuf.message import DecodeError
from google.protobuf.json_format import MessageToJson
sys.path.insert(0, 'protobuf')
import gtfs_realtime_pb2 as gtfsrt

PB_OUTPUT_DIR = "data"

config = {}

if os.environ.get('API_URL') is not None:

	parameters = {'source':os.environ.get('DATASET')}

	req = requests.get(os.environ.get('API_URL')+"/status/config/db-url", params=parameters, timeout=10).json()
	config['DB_URL'] = os.environ.get('DB_URL', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/db-archive", params=parameters, timeout=10).json()
	config['DB_UPLOAD'] = os.environ.get('DB_UPLOAD', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/pb-archive", params=parameters, timeout=10).json()
	config['PB_DOWNLOAD'] = os.environ.get('PB_DOWNLOAD', req['result'])

	config['PB_PATH'] = os.environ.get('PB_PATH', PB_OUTPUT_DIR)
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-request-interval", params=parameters, timeout=10).json()
	config['SLEEP_TIME'] = os.environ.get('SLEEP_TIME', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-request-adaptive", params=parameters, timeout=10).json()
	config['SLEEP_ADAPTIVE'] = os.environ.get('SLEEP_ADAPTIVE', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-trip-enabled", params=parameters, timeout=10).json()
	config['URL_TRIP_UPDATES_ENABLED'] = os.environ.get('URL_TRIP_UPDATES_ENABLED', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-trip-url", params=parameters, timeout=10).json()
	config['URL_TRIP_UPDATES'] = os.environ.get('URL_TRIP_UPDATES', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-vehicle-enabled", params=parameters, timeout=10).json()
	config['URL_VEHICLE_POSITIONS_ENABLED'] = os.environ.get('URL_VEHICLE_POSITIONS_ENABLED', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-vehicle-url", params=parameters, timeout=10).json()
	config['URL_VEHICLE_POSITIONS'] = os.environ.get('URL_VEHICLE_POSITIONS', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-alerts-enabled", params=parameters, timeout=10).json()
	config['URL_ALERTS_ENABLED'] = os.environ.get('URL_ALERTS_ENABLED', req['result'])
	req = requests.get(os.environ.get('API_URL')+"/status/config/gtfsrt-alerts-url", params=parameters, timeout=10).json()
	config['URL_ALERTS'] = os.environ.get('URL_ALERTS', req['result'])

else:
	config['DB_URL'] = os.environ.get('DB_URL')
	config['DB_UPLOAD'] = os.environ.get('DB_UPLOAD')
	config['PB_DOWNLOAD'] = os.environ.get('PB_DOWNLOAD')
	config['PB_PATH'] = os.environ.get('PB_PATH', PB_OUTPUT_DIR)
	config['SLEEP_TIME'] = os.environ.get('SLEEP_TIME')
	config['SLEEP_ADAPTIVE'] = os.environ.get('SLEEP_ADAPTIVE')
	config['URL_TRIP_UPDATES_ENABLED'] = os.environ.get('URL_TRIP_UPDATES_ENABLED')
	config['URL_TRIP_UPDATES'] = os.environ.get('URL_TRIP_UPDATES')
	config['URL_VEHICLE_POSITIONS_ENABLED'] = os.environ.get('URL_VEHICLE_POSITIONS_ENABLED')
	config['URL_VEHICLE_POSITIONS'] = os.environ.get('URL_VEHICLE_POSITIONS')
	config['URL_ALERTS_ENABLED'] = os.environ.get('URL_ALERTS_ENABLED')
	config['URL_ALERTS'] = os.environ.get('URL_ALERTS')

if not config['DB_UPLOAD'] == True and not config['PB_DOWNLOAD'] == True:
	print("You have Protobuffer Download and Database Upload Disabled.")
	print("The program doesn't do anything else.")
	exit()

sleep_time = int(config['SLEEP_TIME'])
gtfsrt_enabled = []
gtfsrt_url = {}
if config['URL_TRIP_UPDATES_ENABLED'] == True:
	gtfsrt_enabled.append('trip_updates')
	gtfsrt_url['trip_updates'] = config['URL_TRIP_UPDATES']
if config['URL_VEHICLE_POSITIONS_ENABLED'] == True:
	gtfsrt_enabled.append('vehicle_positions')
	gtfsrt_url['vehicle_positions'] = config['URL_VEHICLE_POSITIONS']
if config['URL_ALERTS_ENABLED'] == True:
	gtfsrt_enabled.append('alerts')
	gtfsrt_url['alerts'] = config['URL_ALERTS']

if config['DB_UPLOAD'] == True:
	import pymongo

	client = pymongo.MongoClient(config['DB_URL'])
	db = client.get_database()

	for table_name in gtfsrt_enabled:
		timestamp_index_exist = False
		if table_name in db.collection_names():
			index_info = db[table_name].index_information()
			for index in index_info:
				for key in index_info[index]['key']:
					for field in key:
						if field == "header.timestamp":
							timestamp_index_exist = True
		if not timestamp_index_exist:
			print("No Timestamp Index Located for "+table_name+". Creating...")
			db[table_name].create_index(
				[("header.timestamp", pymongo.DESCENDING)],
				unique=True,background=True
			)

while True:

	increase_sleep = False

	for table_name in gtfsrt_enabled:

		try:

			r = requests.get(gtfsrt_url[table_name], timeout=10)
			fm = gtfsrt.FeedMessage()
			fm.ParseFromString(r.content)
			data = json.loads(MessageToJson(fm))

			if config['PB_DOWNLOAD'] == True:
				outputFile = config['PB_PATH']+'/'+data['header']['timestamp']+"_"+table_name+".pb"
				if os.path.isfile(outputFile):
					print(str(data['header']['timestamp']),"- Protobuf File Duplicate on "+outputFile)
					increase_sleep = True				
				f = open(outputFile, 'wb')
				f.write(r.content)
				f.close()
				print(data['header']['timestamp'],"- Protobuf File Written on "+outputFile)

			if config['DB_UPLOAD'] == True:
				data['header']['timestamp'] = int(data['header']['timestamp'])
				try:
					db[table_name].insert_one(data)
					print(str(data['header']['timestamp']),"- DB Inserted to "+table_name+".")
				except pymongo.errors.DuplicateKeyError:
					print(str(data['header']['timestamp']),"- DB Rejected to "+table_name+". Duplicate Keys.")
					increase_sleep = True

		except requests.exceptions.ReadTimeout as e:
			print("Connection Error to: "+gtfsrt_url[table_name])
			print(e)
		except requests.exceptions.ConnectionError as e:
			print("Connection Error to: "+gtfsrt_url[table_name])
			print(e)
		except requests.exceptions.ChunkedEncodingError as e:
			print("Connection Error to: "+gtfsrt_url[table_name])
			print(e)
		except DecodeError:
			print("Unable to decode: "+gtfsrt_url[table_name])
		except KeyError as e:
			print("Missing Value in Protobuffer from: "+gtfsrt_url[table_name])
			print(e)

	if config['SLEEP_ADAPTIVE'] == True and increase_sleep:
		sleep_time = sleep_time + 5
		print("Increased Sleep Time to "+str(sleep_time))
	else: 
		print("Sleeping for "+str(sleep_time))
	time.sleep(sleep_time)
