# tristar.py Python 3 version
Morningstar Tristar MPPT monitor

Version 2.0

sudo pip3 install pymodbus
Check the serialUSB device!  
ls -l /dev

Installed on RPi3 running Stretch in /home/pi/monitor
Run with ~/monitor/python3 tristar.py

Create a service so it starts with the RPi
sudo nano /lib/systemd/system/tristar.service

[Unit]
Description=Tristar MPPT logging service
After=multi-user.target

[Service]
User=pi  (Might be required - runs the service as user pi for pymodbus module)
Type=idle
ExecStart=/usr/bin/python3 /home/pi/monitor/tristar.py

sudo systemctl daemon-reload
sudo systemctl start tristar.service
