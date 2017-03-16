#!/usr/bin/env python
# -*- coding: UTF-8 -*-
########################################################################
#                                                                      #
# /MC_USB_3114.py                                                      #
#                                                                      #
# Copyright 2016, Kevin Wright                                         #
#                                                                      #
# This file is a device class for Measurement Computing USB-3114 DAQs  #
# It was constructed based on the NI board device class included in    #
# in the core modules of Labscript                                     #
########################################################################

import time

from labscript import LabscriptError, AnalogOut
from labscript_devices import labscript_device, BLACS_tab, BLACS_worker, runviewer_parser
import labscript_devices.MCBoard as parent

import numpy as np
import labscript_utils.h5_lock, h5py
import labscript_utils.properties

from UniversalLibrary import UniversalLibrary as UL
from UniversalLibrary import constants as ULC

from multiprocessing import Process
from MCWorker import MC_Task

BoardName = "USB-3114"

@labscript_device
class MC_USB_3114(parent.MCBoard):
    description = 'MC-USB-3114'
    n_analogs = 16
    n_digitals = 8
    n_analog_ins = 0
    clock_limit = 100
    digital_dtype = np.uint8
    
    def generate_code(self, hdf5_file):
        parent.MCBoard.generate_code(self, hdf5_file)
        
        # count the number of analog outputs in use
        analog_count = 0
        for child in self.child_devices:
            if isinstance(child,AnalogOut):
                analog_count += 1    
             
from blacs.tab_base_classes import Worker, define_state
from blacs.tab_base_classes import MODE_MANUAL, MODE_TRANSITION_TO_BUFFERED, MODE_TRANSITION_TO_MANUAL, MODE_BUFFERED  
from blacs.device_base_class import DeviceTab

do_data0 = int('10101010',2)
do_data1 = int('01010101',2)
dummy_do_data = [do_data0, do_data1] * 5
ao_data0 = [0] * 16
ao_data1 = [32768] * 16
dummy_ao_data = [ao_data0, ao_data1] * 5
dummy_time_data = [1,2,3,4,5]


@BLACS_tab
class MC_USB_3114Tab(DeviceTab):
    def initialise_GUI(self):
        # Capabilities
        self.num_AO = 16
        self.num_DO = 8
        self.base_units = 'V'
        self.base_min = 0
        self.base_max = 10.0
        self.base_step = 0.1
        self.base_decimals = 3
        
        # Create the AO output objects
        ao_prop = {}
        for i in range(self.num_AO):
            ao_prop['ao%d'%i] = {'base_unit':self.base_units,
                                 'min':self.base_min,
                                 'max':self.base_max,
                                 'step':self.base_step,
                                 'decimals':self.base_decimals
                                }
        
        do_prop = {}
        for i in range(self.num_DO):
            do_prop['port0/line%d'%i] = {}
            
            
        # Create the output objects    
        self.create_analog_outputs(ao_prop)        
        # Create widgets for analog outputs only
        dds_widgets,ao_widgets,do_widgets = self.auto_create_widgets()
        
        # now create the digital output objects
        self.create_digital_outputs(do_prop)        
        # manually create the digital output widgets so they are grouped separately
        do_widgets = self.create_digital_widgets(do_prop)
        
        def do_sort(channel):
            flag = channel.replace('port0/line','')
            flag = int(flag)
            return '%02d'%(flag)
    
        def ao_sort(channel):
            flag = channel.replace('ao','')
            flag = int(flag)
            return '%02d'%(flag)
            
            
        # and auto place the widgets in the UI
        self.auto_place_widgets(("Analog Outputs",ao_widgets,ao_sort),("Digital Outputs",do_widgets,do_sort))
        
        # Store the device name
        self.name = str(self.settings['connection_table'].find_by_name(self.device_name).BLACS_connection)
        
        # Create and set the primary worker
        self.create_worker("main_worker", MCUSB3114Worker,{'name':self.name, 'limits': [self.base_min,self.base_max], 'num_AO':self.num_AO, 'num_DO': self.num_DO})
        self.primary_worker = "main_worker"

        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False) 
    
    
@BLACS_worker
class MCUSB3114Worker(Worker):
    def init(self):
        exec 'import UniversalLibrary as UL' in globals()
        global pylab; import pylab
        global h5py; import labscript_utils.h5_lock, h5py
        global numpy; import numpy
        
        #TODO: fiugre out how to get these values from the device class?
        self.BoardNum = 0
        self.RANGE = ULC.UNI10VOLTS # = 100
        
        # Initialize the output data for all channels to some funky values for testing
        # TODO: set these values all to zero after initial code debugging is done
        self.ao_data = dummy_ao_data[0]
        self.do_data = dummy_do_data[0]
        self.time_data = dummy_time_data
        
        # Configure digital ports as outputs
        UL.cbDConfigPort(0, ULC.AUXPORT, ULC.DIGITALOUT)
	
        # Write data to the outputs
        self.setup_static_channels()    

    def setup_static_channels(self):
        byte = np.packbits(self.do_data)[0]
        UL.cbDOut(self.BoardNum, ULC.AUXPORT, int(byte) ) # set DO channels to initial default values
        scaled_ao_data = self.fromVolts(self.ao_data)
        for i in range(self.num_AO): 
            UL.cbAOut(self.BoardNum, i, 0, scaled_ao_data[i] ) # set AO channels to their initial defaults

    def program_manual(self,front_panel_values):
        self.ao_data = [ front_panel_values['ao%d'%i] for i in range(self.num_AO)]
        self.do_data = [ front_panel_values['port0/line%d'%i] for i in range(self.num_DO)]
        self.setup_static_channels()
        
    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        # Store the initial values in case we have to abort and restore them:
        # TODO: Coerce/quantise these correctly before returning them
        self.initial_values = initial_values
            
        with h5py.File(h5file,'r') as hdf5_file:
            group = hdf5_file['devices/'][device_name]
            device_properties = labscript_utils.properties.get(hdf5_file, device_name, 'device_properties')
            connection_table_properties = labscript_utils.properties.get(hdf5_file, device_name, 'connection_table_properties')
            h5_data = group.get('ANALOG_OUTS')
            if h5_data:
                self.buffered_using_analog = True
                ao_channels = device_properties['analog_out_channels']
                ao_data = pylab.array(h5_data,dtype=np.float64)[:-1,:]
            else:
                self.buffered_using_analog = False   
                
            h5_data = group.get('DIGITAL_OUTS')
            if h5_data:
                self.buffered_using_digital = True
                do_channels = device_properties['digital_lines']
                do_bitfield = numpy.array(h5_data,dtype=numpy.uint32)
            else:
                self.buffered_using_digital = False            
            
            do_write_data = numpy.zeros((do_bitfield.shape[0],self.num_DO),dtype=numpy.uint8)
            for i in range(self.num_DO):
                do_write_data[:,i] = (do_bitfield & (1 << i)) >> i
                
        #self.MC_Process = Process(name="MCworker", target=MCWorker, args=(dummy_ao_data, dummy_do_data, dummy_time_data))  
        #self.MC_Process.start()
        time.sleep(1) # wait to allow new process to spawn before continuing
        
        print(ao_channels)
        print(ao_data)
        
        print(do_channels)
        print(self.do_data)
        print(do_bitfield)
        
        print(self.time_data)
                
    def fromVolts(self, values):
	    return [ UL.cbFromEngUnits(BoardNum = 0, Range = ULC.UNI10VOLTS, EngUnits = val, DataVal = 0) for val in values]

    def toVolts(self, values):
        return [ UL.cbToEngUnits(BoardNum = 0, Range = ULC.UNI10VOLTS, DataVal = val, EngUnits = 0.0) for val in values]
		
    def outrange(self, volt_value):
        dummyref = 0
        return int(UL.cbFromEngUnits(self.BoardNum, self.RANGE, volt_value, dummyref)  )
            
    def transition_to_manual(self,abort=False):
        # if aborting, don't call StopTask since this throws an
        # error if the task hasn't actually finished!
        self.setup_static_channels()
        if abort:
            # Reprogram the initial states:
            self.program_manual(self.initial_values)           
        return True
        
    def abort_transition_to_buffered(self):
        # TODO: untested
        return self.transition_to_manual(True)
        
    def abort_buffered(self):
        # TODO: untested
        return self.transition_to_manual(True)    

             
@runviewer_parser
class RunviewerClass(parent.RunviewerClass):
    num_digitals = 0
    
