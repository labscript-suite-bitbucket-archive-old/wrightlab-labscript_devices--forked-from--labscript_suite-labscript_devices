# -*- coding: utf-8 -*-
"""
Created on Sat Mar 11 16:14:51 2017

@author: Kevin
"""
import numpy as np
from UniversalLibrary import UniversalLibrary as UL
from UniversalLibrary import constants as ULC
import time

def MC_Task(ao_data, do_data, time_data):
    
    BoardNum = 0         # for USB-3114, set in InstaCal, or by config functions
    LowChan = 0          #
    HighChan = 15        #
    NumPoints = 16       # Total number of points to output.
    Rate = 0             # Rate can't be set for this board.
    Range = 0            # Has to be set in Instacal (or config function??)
    zero32 = np.uint32(0)
    
    # Set all digital ports to output
    UL.cbDConfigPort(BoardNum, ULC.AUXPORT, ULC.DIGITALOUT)
    
    # Clear the counter 
    UL.cbCLoad32( BoardNum, RegNum = ULC.LOADREG1, LoadValue = 0)
    # Dummy value for the counter (is this even necessary?)
    
    print("Beginning MC_Task output")
    
    # pre-programming data for analog step 0
    step = 0
    UL.cbAOutScan(BoardNum, LowChan, HighChan, NumPoints, Rate, Range, ao_data[0], ULC.SIMULTANEOUS)
    print("Programmed ao_data for step 0")
    
    while True:
        count = UL.cbCIn32(BoardNum, CounterNum = 1, Count = zero32)
        if count < step:
            time.sleep(0.01)
            continue
        if count == step:
            UL.cbDOut(BoardNum, PortNum = 1, DataValue = do_data[step])
            print("Output digital values for step %d" % step)  
            step = step + 1
            if step == len(time_data):
                break
            else:
                UL.cbAOutScan(BoardNum, LowChan, HighChan, NumPoints, Rate, Range, ao_data[step], ULC.SIMULTANEOUS)
                print("Pre-programmed ao_data for step %d" % step)
                continue                
        if count > step :
            print("Steps %d through %d were skipped, output rate too high!" % (step, count-1) )
        
    print("I think we're all done here?")       
            
            
if __name__ == "__main__":
    ao_data0 = np.zeros(16, dtype=np.int16)
    ao_data1 = np.array([60000, 60000, 60000, 60000, 60000, 60000, 60000, 60000, 
                         60000, 60000, 60000, 60000, 60000, 60000, 60000, 60000], dtype = np.int16)
    ao_data = [ao_data0, ao_data1, ao_data0, ao_data1, ao_data0, ao_data1, ao_data0, ao_data1, ao_data0 ]
    
    do_data0 = '0b01010101'
    do_data1 = '0b10101010'
    do_data = [do_data0, do_data1, do_data0, do_data1, do_data0, do_data1, do_data0, do_data1, do_data0 ]
    
    time_data = [1,2,3,4,5,6,7,8,9]
    
    MC_Task(ao_data, do_data, time_data)