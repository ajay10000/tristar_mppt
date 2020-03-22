#!/usr/bin/python3
# Monitor Tristar MPPT solar charger and optionally log to Domoticz and/or CSV data file

import time, datetime, requests, logging
import os.path
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

# Begin user editable variables
logger_name = "tristar"   #used for log file names, messages, etc
debug_level='info'       # debug options DEBUG, INFO, WARNING, ERROR, CRITICAL
delay_time = 30           #update time in seconds
domain="http://rpi4:8080"
# Specify the serial client.  See /etc/udev/rules.d/99_usbdevices.rules for tristarUSB device
client = ModbusClient(method='rtu', port='/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0', baudrate=9600, parity = 'N', bytesize = 8, stopbits = 1)  # by-id replaces /dev/ttyUSB1
# Define the device state list
state = ['Start', 'Night Check', 'Disconnected', 'Night', 'Fault!', 'BulkCharge', 'Absorption', 'FloatCharge', 'Equalizing']
monitor_list = ["batV","batI","statenum","pwrOut","batVmin","batVmax","ampH"]
idx = [77,78,80,87,82,83,85]  # Domoticz index values for monitor_list
dataFile_columns = "Time," + "Bat V," + "Bat I," + "Pwr In," + "AHr," + "State"   # set to empty "" to disable data logging to CSV file
dailyFile_columns = "Date-Time,Bat V max,Bat V min,AHr,WHr,Abs T,Equ T,Flt T"
# End user editable variables

log_path = os.path.dirname(os.path.realpath(__file__)) 
dailyFile = log_path + "/" + logger_name + "_daily.csv"
dataFile = log_path + "/" + logger_name + "_data.csv"
batI = 0                  # define current as global so it keeps previous value if invalid (159A bug)
previous_out = ""         # variable to prevent logging the same values
baseURL = domain + "/json.htm?type=command&param=udevice"
log_level = getattr(logging, debug_level.upper(), 10)
logging.basicConfig(filename=log_path + "/" + logger_name + ".log", level=log_level, format="%(asctime)s:%(name)s:%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)
logger.warning('\r\n')  # Blank line between (re)starts
logger.warning(logger_name + " (re)started monitoring")

class tristar:
  def __init__(self):
    # Set up headers for log and daily files if required
    if dataFile_columns != "":
      if not os.path.isfile(dataFile):
        out = dataFile_columns + "\n"
        try:
          fil = open(dataFile, 'w')
          fil.write(out)
        except IOError as e:
          logger.error("I/O error({}): {}".format(e.errno, e.strerror))
        else:
          fil.close()

      if not os.path.isfile(dailyFile):
        out = dailyFile_columns + "\n"
        try:
          fil = open(dailyFile, 'w')
          fil.write(out)
        except IOError as e:
          logger.error("I/O error({0}): {1}".format(e.errno, e.strerror))
        else:
          fil.close()

    self.one_day = datetime.timedelta(days=1)
  
  def modbusConnect(self):
    # Connect to the Modbus client
    try:
      connection = client.connect()
      logger.debug("Connected: {} to {}".format(connection,client))
    except IOError:
      logger.error("Cannot connect to {}".format(client.port))
      return False   #raise SystemExit()
        
  def read_registers(self):
    global batI
    global previous_out
    nextDailyTime = datetime.datetime.combine(datetime.date.today() + self.one_day,datetime.time(23,55,0))
    if self.modbusConnect() == False:
      return False
    #read the registers from logical address 0
    rr = client.read_holding_registers(0x00,92,unit=0x01)
    logger.debug("rr: {}".format(rr))
    if rr == None:
      client.close()
      logger.error("No comms. Check USB port")
      return False  #raise SystemExit()

    # for all indexes, subtract 1 from what's in the manual
    V_PU_hi = rr.registers[0]
    V_PU_lo = rr.registers[1]
    I_PU_hi = rr.registers[2]
    I_PU_lo = rr.registers[3]
    V_PU = float(V_PU_hi) + float(V_PU_lo)
    I_PU = float(I_PU_hi) + float(I_PU_lo)
    v_scale = V_PU * 2**(-15)
    i_scale = I_PU * 2**(-15)
    p_scale = V_PU * I_PU * 2**(-17)
    
    batV = '{:.2f}'.format(rr.registers[24] * v_scale)
    # fix intermittent 159A output, especially around dusk
    if rr.registers[28] * i_scale < 150:
      batI = '{:.2f}'.format(rr.registers[28] * i_scale)
    aryV = '{:.2f}'.format(rr.registers[27] * v_scale)
    aryI = '{:.2f}'.format(rr.registers[29] * i_scale)
    statenum = '{}'.format(state[rr.registers[50]])
    hskT = '{:.2f}'.format(rr.registers[35])
    rtsT = '{:.2f}'.format(rr.registers[36])
    pwrOut = '{:.2f}'.format(rr.registers[58] * p_scale)
    #logger.warning("Power out: {}".format(pwrOut))
    pwrIn = '{:.2f}'.format(rr.registers[59] * p_scale)
    batVmin = '{:.2f}'.format(rr.registers[64] * v_scale)
    batVmax = '{:.2f}'.format(rr.registers[65] * v_scale)
    ampH = '{:.2f}'.format(rr.registers[67] * 0.1)
    watH = '{:.2f}'.format(rr.registers[68])
    absT = '{:.2f}'.format(rr.registers[77])
    equT = '{:.2f}'.format(rr.registers[78])
    fltT = '{:.2f}'.format(rr.registers[79])
    #dipswitches = bin(rr.registers[48])[::-1][:-2].zfill(8)
    #logger.debug "dipswitches:     %s" % dipswitches
    #logger.debug "dipswitches:     12345678"
    logger.info("Bat V: {}, Bat I: {}, Ary V: {}".format(batV,batI,aryV))  

    try:
      for i in range(0,len(monitor_list)): # range is 0 based
        full_url = baseURL + "&idx={}&nvalue=0&svalue={}".format(idx[i],eval(monitor_list[i]))
        logger.debug("URL: {}".format(full_url))
        # Send the json string
        response = requests.get(full_url)
    except:
      logger.error("Connection failed to {}".format(domain))
   
    #except urllib2.HTTPError as e:
      # Error checking to prevent crashing on bad requests
    #  logger.error("HTTP error({}): {}".format(e.errno, e.strerror))
    #except requests.URLError as e:   #urllib2.URLError as e:
    #  logger.error("URL error({}): {}".format(e.errno, e.strerror))
    
    if dataFile_columns != "":
      out = time.strftime("%Y-%m-%d %H:%M") + "," + batV + "," + batI + "," + pwrIn + "," + ampH + "," + statenum + "\n"
      if out[18:] != previous_out: # Don't log the data if it is identical (typically at night).
        previous_out = out[18:]
        try:
          fil = open(dataFile, 'a')
          fil.write(out)
        except IOError as e:
          logger.error("I/O error({}): {}".format(e.errno, e.strerror))
        else:
          fil.close()

        if datetime.datetime.now() > nextDailyTime:
          nextDailyTime = datetime.datetime.combine(datetime.date.today() + self.one_day,datetime.time(23,55,0))
          out = time.strftime("%Y-%m-%d %H:%M") + "," + batVmin + "," + batVmax + "," + ampH + "," + watH + "," + absT  + "," + equT + "," + fltT + "\n"
          try:
            fil = open(dailyFile, 'a')
            fil.write(out)
          except IOError as e:
            logger.error("I/O error({0}): {1}".format(e.errno, e.strerror))
          else:
            fil.close()

print("starting...")

if __name__ == '__main__':
  ts = tristar()
  while True:
    ts.read_registers()
    time.sleep(delay_time)
    
  client.close()
