import struct
def read_str(d,o):
    n=struct.unpack_from("<Q",d,o)[0]; o+=8
    return d[o:o+n].decode("utf-8",errors="replace"), o+n
def read_val(d,o,t):
    if t==8: return read_str(d,o)
    if t==9:
        et=struct.unpack_from("<I",d,o)[0]; o+=4
        n=struct.unpack_from("<Q",d,o)[0]; o+=8
        for _ in range(n): _,o=read_val(d,o,et)
        return None,o
    sizes={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
    return None, o+(sizes.get(t) or 0)
path=r"C:/Users/Njoro/Downloads/Hy-MT2-1.8B-1.25Bit.gguf"
data=open(path,"rb").read(); fsize=len(data)
o=4+4; tc=struct.unpack_from("<Q",data,o)[0]; o+=8; kv=struct.unpack_from("<Q",data,o)[0]; o+=8
seen=set()
for i in range(kv):
    k,o=read_str(data,o); t=struct.unpack_from("<I",data,o)[0]; o+=4; _,o=read_val(data,o,t)
    if k in ("general.architecture","general.name","general.file_type","general.alignment"):
        print(k,"=",data[o-200:o+0][-200:] if t==8 else t)
    if k=="general.architecture":
        pass
while (o%32): o+=1
print("--- first 6 tensor infos ---")
for i in range(tc):
    name,o=read_str(data,o)
    nd=struct.unpack_from("<I",data,o)[0]; o+=4
    dims=list(struct.unpack_from("<%dQ"%nd,data,o)); o+=8*nd
    tt=struct.unpack_from("<I",data,o)[0]; o+=4
    tf=struct.unpack_from("<Q",data,o)[0]; o+=8
    seen.add(tt)
    if i<6:
        print(i,name,"typeid",tt,"dims",tuple(dims),"off",tf)
print("distinct type ids in first 6:", sorted(seen))
