# r1: kantor pusat. ether2 = LAN-A, ether3 = link ke r2.
/ip address
add address=10.10.0.1/24 interface=ether2 comment="LAN-A"
add address=10.0.12.1/30 interface=ether3 comment="link r1-r2"
/routing ospf instance
add name=default version=2 router-id=1.1.1.1
/routing ospf area
add name=backbone area-id=0.0.0.0 instance=default
/routing ospf interface-template
add area=backbone networks=10.10.0.0/24
add area=backbone networks=10.0.12.0/30
