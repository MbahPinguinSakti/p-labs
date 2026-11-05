# r2: router transit. ether2 = link ke r1, ether3 = link ke r3.
/ip address
add address=10.0.12.2/30 interface=ether2 comment="link r1-r2"
add address=10.0.23.1/30 interface=ether3 comment="link r2-r3"
/routing ospf instance
add name=default version=2 router-id=2.2.2.2
/routing ospf area
add name=backbone area-id=0.0.0.0 instance=default
/routing ospf interface-template
add area=backbone networks=10.0.12.0/30
add area=backbone networks=10.0.23.0/30
