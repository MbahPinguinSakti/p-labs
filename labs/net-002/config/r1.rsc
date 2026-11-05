# r1: kantor pusat. ether2 = LAN-A, ether3 = link ke r2.
/ip address
add address=10.10.0.1/24 interface=ether2 comment="LAN-A"
add address=10.0.12.1/30 interface=ether3 comment="link r1-r2"
/ip route
add dst-address=10.20.0.0/24 gateway=10.0.12.2 comment="LAN-B lewat r2"
