#!/usr/bin/env python
 
# import normal packages
import platform 
import logging
import sys
import os
import sys
if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject
import sys
import time
import requests # for http GET
import configparser # for config/ini file
 
# our own packages from victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService


class DbusSolaxX1Service:
  def __init__(self, servicename, deviceinstance, paths, productname='Solax X1', connection='192.168.2.111- 126 (sunspec)'):
    self._dbusservice = VeDbusService("{}.pv_{}".format(servicename, self._getSolaxInverterSerial()))
    self._paths = paths
 
    logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))
 
    # Create the management objects, as specified in the ccgx dbus-api document
    self._dbusservice.add_path('/Mgmt/ProcessName', __file__) #?
    self._dbusservice.add_path('/Mgmt/ProcessVersion', '1.4.17') #fixed value from fronius-sim 1.4.17
    self._dbusservice.add_path('/Mgmt/Connection', connection)
 
    # Create the mandatory objects    
    self._dbusservice.add_path('/Connected', 1)
    self._dbusservice.add_path('/CustomName', productname)        
    self._dbusservice.add_path('/DeviceInstance', deviceinstance)
    self._dbusservice.add_path('/ErrorCode', 0)
    self._dbusservice.add_path('/FirmwareVersion', 1)
    self._dbusservice.add_path('/Position', self._getInverterPosition()) 
    self._dbusservice.add_path('/ProductId', 41284, gettextcallback = lambda p, v: ('a144')) #copy from working version - see fronius-sim
    self._dbusservice.add_path('/ProductName', productname)
    self._dbusservice.add_path('/Serial', self._getSolaxInverterSerial())
    self._dbusservice.add_path('/StatusCode', 11, gettextcallback = lambda p, v: ('Running (MPPT)'))
    self._dbusservice.add_path('/Ac/MaxPower', self._getInverterMaxPower())
    self._dbusservice.add_path('/Ac/PowerLimit', None)
    self._dbusservice.add_path('/UpdateIndex', 0)

    # add path values to dbus
    for path, settings in self._paths.items():
      self._dbusservice.add_path(
        self._replacePhaseVar(path), settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue)
 
    # last update
    self._lastUpdate = 0
    self._lastCloudUpdate = 0
    self._lastCloudCheck = 0    
    self._lastCloudACPower = 0
    self._lastCloudInverterStatus = 0
 
    # add _update function 'timer'
    gobject.timeout_add(500, self._update) # call update routine
 
    # add _signOfLife 'timer' to get feedback in log every 5minutes
    gobject.timeout_add(self._getSignOfLifeInterval()*60*1000, self._signOfLife)

 
  def _getInverterPosition(self):
    config = self._getConfig()
    #Debug infos: 0=AC input 1; 1=AC output; 2=AC input 2
    return int(config['INVERTER']['Position'])


  def _getSignOfLifeInterval(self):
    config = self._getConfig()
    value = config['DEFAULT']['SignOfLifeLog']
    
    if not value: 
        value = 0
    
    return int(value)  

 
  def _getSolaxInverterSerial(self):
    data = self._getSolaxCloudData()  
    
    if not data['result']['inverterSN']:
        raise ValueError("Response does not contain 'mac' attribute")
    
    serial = data['result']['inverterSN']
    return serial
 
 
  def _getConfig(self):
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    return config;
 

  def _getPhaseFromConfig(self):
    result = "L1"
    config = self._getConfig()
    result = config['INVERTER']['Phase']
    return result
    
  
  def _replacePhaseVar(self, input):
    result = input
    result = result.replace("[*Phase*]", self._getPhaseFromConfig())
    return result
    
  
  def _getSolaxCloudUrl(self):
    config = self._getConfig()
    endpoint = config['SOLAXCLOUD']['Endpoint']
    tokenId = config['SOLAXCLOUD']['TokenId']
    regNo = config['SOLAXCLOUD']['RegNo']
    
    if endpoint == "": 
        raise ValueError("Solax Cloud endpoint is not set/empty")
        
    if tokenId == "": 
        raise ValueError("Solax Cloud tokenId is not set/empty")
    
    if regNo == "": 
        raise ValueError("Solax Cloud regNo is not set/empty")
    
    
    URL = "%s?tokenId=%s&sn=%s" % (endpoint, tokenId, regNo)
    
    return URL
    
 
  def _getSolaxCloudData(self):
    URL = self._getSolaxCloudUrl()
    data_r = requests.get(url = URL)
    
    # check for response
    if not data_r:
        raise ConnectionError("No response from Solax Cloud - %s" % (URL))
    
    data = data_r.json()     
    
    # check for Json
    if not data:
        raise ValueError("Converting response to JSON failed")
     
    # check for success
    if data['success'] != True:
        raise ValueError("Response (%s) is not ok - 'success'=%s 'exception'=%s" % ( URL, data['success'], data['exception']))
        
    return data
 
 
  def _getInverterStatus(self, solaxInverterStatusCode: int):    
    status = 10
    
    if solaxInverterStatusCode in (100,101) :
        status = 0
    
    if solaxInverterStatusCode == 102:
        status = 7
    
    if solaxInverterStatusCode in (103,104):
        status = 10
    
    if solaxInverterStatusCode in (105,106,107,108):
        status = 9
    
    if solaxInverterStatusCode in (109,110):
        status = 8
    
    if solaxInverterStatusCode in (111,112,113):
        status = 5
    
    return status
    

  def _getGridVoltage(self):
    config = self._getConfig()    
    return int(config['INVERTER']['GridVoltage'])
 

  def _getInverterMaxPower(self):
    config = self._getConfig()    
    return int(config['INVERTER']['MaxPower'])


  def _signOfLife(self):
    logging.info("--- Start: sign of life ---")
    logging.info("Last _update() call: %s" % (self._lastUpdate))
    logging.info("Last _updateCloud() call: %s" % (self._lastCloudUpdate))
    logging.info("Last '/Ac/Power' (Cloud): %s" % (self._lastCloudACPower))
    logging.info("Last '/Ac/Power': %s" % (self._dbusservice['/Ac/Power']))
    logging.info("--- End: sign of life ---")
    return True
  

  def _predictACPowerValue(self, lastUpdate, lastValue, lastValueChangePercSecond):
    return lastValue*((1+((time.time() - lastUpdate)*lastValueChangePercSecond)))  
 
  def _update(self):
    try:  
       # logging
       logging.debug("---");
    
       # some general data
       grid_voltage = self._getGridVoltage()          
           
       #send data to DBus
       if self._lastCloudCheck == 0 or (time.time()-self._lastCloudCheck) >= 15:
          #get data from Solax Cloud
          meter_data = self._getSolaxCloudData()
          self._lastCloudCheck = time.time()
          
          # extract values
          self._lastCloudUpdate = time.time()
          self._lastCloudACPower = meter_data['result']['acpower']
          self._lastCloudACEnergyTotal = meter_data['result']['yieldtotal']
          self._lastCloudInverterStatus = int(meter_data['result']['inverterStatus'])
           
          # logging
          logging.debug("Cloud Update - Solax status-code: %s" % (self._lastCloudInverterStatus))
          logging.debug("Cloud Update - Inverter status-code: %s" % (self._getInverterStatus(self._lastCloudInverterStatus)))
          logging.debug("Cloud Update - AC power: %s" % (self._lastCloudACPower))
          logging.debug("Cloud Update - AC energy total: %s" % (self._lastCloudACEnergyTotal))
       

              
       # set normal values       
       self._dbusservice['/Ac/Power'] = self._lastCloudACPower
       self._dbusservice['/StatusCode'] = self._getInverterStatus(self._lastCloudInverterStatus)  
       self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Voltage')] = grid_voltage
       self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Current')] = round(self._dbusservice['/Ac/Power'] / self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Voltage')] , 2)
       self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Power')] = self._dbusservice['/Ac/Power']
       self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Energy/Forward')] = self._lastCloudACEnergyTotal
       self._dbusservice['/Ac/Energy/Forward'] = self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Energy/Forward')]    # one phase pv-inverter #  + self._dbusservice['/Ac/L2/Energy/Forward'] + self._dbusservice['/Ac/L3/Energy/Forward']
       self._dbusservice['/Ac/Current'] = self._dbusservice[self._replacePhaseVar('/Ac/[*Phase*]/Current')] # just copy value - 1phase inverter
       self._dbusservice['/Ac/Voltage'] = grid_voltage
              
       
       # update lastupdate vars
       self._lastUpdate = time.time()   
       
       # increment UpdateIndex - to show that new data is available
       index = self._dbusservice['/UpdateIndex'] + 1  # increment index
       if index > 255:   # maximum value of the index
         index = 0       # overflow from 255 to 0
       self._dbusservice['/UpdateIndex'] = index       
       
       # logging
       logging.debug("Inverter power: %s" % (self._dbusservice['/Ac/Power']))
       logging.debug("---");
       
       
    except Exception as e:
       logging.critical('Error at %s', '_update', exc_info=e)

    # return true, otherwise add_timeout will be removed from GObject - see docs http://library.isr.ist.utl.pt/docs/pygtk2reference/gobject-functions.html#function-gobject--timeout-add
    return True
 
 
  def _handlechangedvalue(self, path, value):
    logging.debug("someone else updated %s to %s" % (path, value))
    return True # accept the change
 


def main():
  #configure logging
  logging.basicConfig(      format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO,
                            handlers=[
                                logging.FileHandler("%s/current.log" % (os.path.dirname(os.path.realpath(__file__)))),
                                logging.StreamHandler()
                            ])
 
  try:
      logging.info("Start");
  
      from dbus.mainloop.glib import DBusGMainLoop
      # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
      DBusGMainLoop(set_as_default=True)
     
      #formatting 
      _kwh = lambda p, v: (str(round(v, 2)) + ' KWh')
      _a = lambda p, v: (str(round(v, 1)) + ' A')
      _w = lambda p, v: (str(round(v, 1)) + ' W')
      _v = lambda p, v: (str(round(v, 1)) + ' V')   
     
      #start our main-service
      pvac_output = DbusSolaxX1Service(
        servicename='com.victronenergy.pvinverter',
        deviceinstance=23, #pvinverters from 20-29
        paths={
          '/Ac/Energy/Forward': {'initial': 0, 'textformat': _kwh},     
          '/Ac/Power': {'initial': 0, 'textformat': _w},
          
          '/Ac/Current': {'initial': 0, 'textformat': _a},
          '/Ac/Voltage': {'initial': 0, 'textformat': _v},
          
          '/Ac/[*Phase*]/Voltage': {'initial': 0, 'textformat': _v},
          '/Ac/[*Phase*]/Current': {'initial': 0, 'textformat': _a},
          '/Ac/[*Phase*]/Power': {'initial': 0, 'textformat': _w},
          '/Ac/[*Phase*]/Energy/Forward': {'initial': 0, 'textformat': _kwh},          
        })
     
      logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
      mainloop = gobject.MainLoop()
      mainloop.run()
  except Exception as e:
    logging.critical('Error at %s', 'main', exc_info=e)
if __name__ == "__main__":
  main()
