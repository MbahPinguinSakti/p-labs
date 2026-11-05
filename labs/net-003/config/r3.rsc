# r3: kantor cabang C. ether2 = link ke r2, ether3 = LAN-C.
/ip address
add address=10.0.23.2/30 interface=ether2 comment="link r2-r3"
add address=10.30.0.1/24 interface=ether3 comment="LAN-C"
/routing ospf instance
add name=default version=2 router-id=3.3.3.3
/routing ospf area
add name=backbone area-id=0.0.0.0 instance=default
/routing ospf interface-template
add area=backbone networks=10.0.23.0/30
add area=backbone networks=10.30.0.0/24
