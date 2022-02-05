#  midi2vjoy.py
#  
#  Copyright 2017  <c0redumb>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  

import sys, os, time, traceback
import ctypes
from optparse import OptionParser
import pygame.midi
import winreg

# Constants
# Axis mapping
axis = {'X': 0x30, 'Y': 0x31, 'Z': 0x32, 'RX': 0x33, 'RY': 0x34, 'RZ': 0x35,
		'SL0': 0x36, 'SL1': 0x37, 'WHL': 0x38, 'POV': 0x39}
		
# Globals
options = None

def midi_test():
	n = pygame.midi.get_count()

	# List all the devices and make a choice
	print('Input MIDI devices:')
	for i in range(n):
		info = pygame.midi.get_device_info(i)
		if info[2]:
			print(i, info[1].decode())
	d = int(input('Select MIDI device to test: '))
	
	# Open the device for testing
	try:
		print('Opening MIDI device:', d)
		m = pygame.midi.Input(d)
		print('Device opened for testing. Use ctrl-c to quit.')
		while True:
			while m.poll():
				raw = m.read(1)
				key = tuple(raw[0][0][0:2])
				if key[0] != 248:
					print(raw)
			time.sleep(0.01)
	except:
		m.close()
		
def read_conf(conf_file):
	'''Read the configuration file'''
	table = {}
	repeaters = {}
	vids = []
	with open(conf_file, 'r') as f:
		for l in f:
			if len(l.strip()) == 0 or l[0] == '#':
				continue
			fs = l.split()
			key = (int(fs[0]), int(fs[1]))
			if len(fs) == 6:
				#This is a repeater, so append the values to the table or add them as-is if this is the first time we've seen this key.
				val = (int(fs[2]), fs[3], fs[4], fs[5])
				if key in table:
					table[key] = [table[key], val]
				else:
					table[key] = val
			else: 
				val = (int(fs[2]), fs[3])
				table[key] = val
			vid = int(fs[2])
			if not vid in vids:
				vids.append(vid)
	return (table, vids)
		
def joystick_run():
	# Process the configuration file
	if options.conf == None:
		print('Must specify a configuration file')
		return
	try:
		if options.verbose:
			print('Opening configuration file:', options.conf)
		(table, vids) = read_conf(options.conf)
		#print(table)
		#print(vids)
	except:
		print('Error processing the configuration file:', options.conf)
		return
		
	# Getting the MIDI device ready
	if options.midi == None:
		print('Must specify a MIDI interface to use')
		return
	try:
		if options.verbose:
			print('Opening MIDI device:', options.midi)
		midi = pygame.midi.Input(options.midi)
	except:
		print('Error opting MIDI device:', options.midi)
		return
		
	# Load vJoysticks
	try:
		# Load the vJoy library
		# Load the registry to find out the install location
		vjoyregkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{8E31F76F-74C3-47F1-9550-E041EEDC5FBB}_is1')
		installpath = winreg.QueryValueEx(vjoyregkey, 'InstallLocation')
		winreg.CloseKey(vjoyregkey)
		#print(installpath[0])
		dll_file = os.path.join(installpath[0], 'x64', 'vJoyInterface.dll')
		vjoy = ctypes.WinDLL(dll_file)
		#print(vjoy.GetvJoyVersion())
		
		# Getting ready
		for vid in vids:
			if options.verbose:
				print('Acquiring vJoystick:', vid)
			assert(vjoy.AcquireVJD(vid) == 1)
			assert(vjoy.GetVJDStatus(vid) == 0)
			vjoy.ResetVJD(vid)
	except:
		#traceback.print_exc()
		print('Error initializing virtual joysticks')
		return
	
	try:
		if options.verbose:
			print('Ready. Use ctrl-c to quit.')
		#Initialise history
		previous_key = None
		previous_vjoy_device = None
		value_cache = {}
		up_vjoy = None
		down_vjoy = None
		while True:
			while midi.poll():
				ipt = midi.read(1)
				#print(ipt)
				key = tuple(ipt[0][0][0:2])
				reading = ipt[0][0][2]
				# Filter out 248 clock messages.
				if key[0] != 248:
					print(key, reading)
				# Check that the input is defined in table
				if not key in table:
					# If key isn't in table, it may be cancelling a previous key.
					# Ignore clock messages and check read value.
					if key[0] != 248 and reading == 0 and previous_key and previous_vjoy_device:
						vjoy.SetBtn(reading, previous_key, int(previous_vjoy_device))
						print("Zeroing previous key press")
					elif key[0] != 248:
						print("Key not specified in conf file")
					continue
				opt = table[key]
				if options.verbose:
					print(key, '->', opt, reading)
				if key[0]:
					# An input
					# Check if it is configured as an axis or a button or a repeater
					# Note: We did not check if that axis is defined in vJoy
					if not opt[1] in axis:
						# A button or repeater input.
						if type(opt) == list:
							#A repeater!
							print('A repeater!')
							#Determine which vjoy is the 'up' key and which vjoy is the 'down' key
							for element in opt:
								if element[3] == 'up':
									up_vjoy = (element[0], element[1])
								elif element[3] == 'down':
									down_vjoy = (element[0], element[1])
								else:
									print("Repeat up or down key not specified. Ensure the config line includes all of: 'vjoy_device	vjoy_button	rep	up' and 'vjoy_device	vjoy_button	rep	down'")							

							#Check if we've seen this key being pressed before or not.
							if key in value_cache:
								#We have seen this key before and have its old value. We can continue.
								#See if the value is increasing or decreasing:
								diff = reading - value_cache[key]
								if diff > 0:
									#Value is increasing
									print('Increasing. Activating up repeater.')
									print(up_vjoy)								
									#Press the 'up' key
									vjoy.SetBtn(1, up_vjoy[0], int(up_vjoy[1]))
									time.sleep(0.001)
									vjoy.SetBtn(0, up_vjoy[0], int(up_vjoy[1]))
								elif diff < 0:
									#Value is decreasing
									print('Decreasing. Activating down repeater.')		
									print(down_vjoy)							
									#Press the 'down' key
									vjoy.SetBtn(1, down_vjoy[0], int(down_vjoy[1]))
									time.sleep(0.001)
									vjoy.SetBtn(0, down_vjoy[0], int(down_vjoy[1]))
								elif diff == 0:
									#Value hasn't changed. Do nothing.
									print('No change')
							else:
								#This must be the first time we've seen an input so don't know which direction it is going in.
								#Will need to wait for another input to take any action.
								print("First ever input.")							
							#Record latest button value for future comparison.
							value_cache[key] = reading					
						else:
							#A normal button
							vjoy.SetBtn(reading, opt[0], int(opt[1]))
							print('Button value sent')
							previous_key = opt[0]
							previous_vjoy_device = opt[1]
					elif opt[1] in axis:
						# An Axis Input
						reading = (reading + 1) << 8
						vjoy.SetAxis(reading, opt[0], axis[opt[1]])
						print('Axis value sent')
			time.sleep(0.001)

	except:
		#traceback.print_exc()
		pass
		
	# Relinquish vJoysticks
	for vid in vids:
		if options.verbose:
			print('Relinquishing vJoystick:', vid)
		vjoy.RelinquishVJD(vid)
	
	# Close MIDI device
	if options.verbose:
		print('Closing MIDI device')
	midi.close()
		
def main():
	# parse arguments
	parser = OptionParser()
	parser.add_option("-t", "--test", dest="runtest", action="store_true",
					  help="To test the midi inputs")
	parser.add_option("-m", "--midi", dest="midi", action="store", type="int",
					  help="File holding the list of file to be checked")
	parser.add_option("-c", "--conf", dest="conf", action="store",
					  help="Configuration file for the translation")
	parser.add_option("-v", "--verbose",
						  action="store_true", dest="verbose")
	parser.add_option("-q", "--quiet",
						  action="store_false", dest="verbose")
	global options
	(options, args) = parser.parse_args()
	
	pygame.midi.init()
	
	if options.runtest:
		midi_test()
	else:
		joystick_run()
	
	pygame.midi.quit()

if __name__ == '__main__':
	main()
