# r2: ruang server. ether2 = link ke r1, ether3 = LAN-B.
/ip address
add address=10.0.12.2/30 interface=ether2 comment="link r1-r2"
add address=10.20.0.1/24 interface=ether3 comment="LAN-B"
/ip route
add dst-address=10.10.0.0/24 gateway=10.0.12.1 comment="LAN-A lewat r1"
