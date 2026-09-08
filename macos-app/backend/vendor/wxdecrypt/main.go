package main
import("encoding/json";"fmt";"io";"os";"strconv")
func main(){
 var p struct{Path string `json:"path"`; Key string `json:"key"`}
 if e:=json.NewDecoder(os.Stdin).Decode(&p);e!=nil{fail("invalid input")}
 key,e:=strconv.ParseUint(p.Key,10,64);if e!=nil{fail("invalid uint64 key")}
 f,e:=os.OpenFile(p.Path,os.O_RDWR,0);if e!=nil{fail("cannot open media")};defer f.Close()
 b:=make([]byte,131072);n,e:=io.ReadFull(f,b);if e!=nil&&e!=io.EOF&&e!=io.ErrUnexpectedEOF{fail("read failed")}
 if n==0{fail("empty media")};DecryptData(b[:n],uint32(n),key)
 if _,e=f.WriteAt(b[:n],0);e!=nil{fail("write failed")}
}
func fail(s string){fmt.Fprintln(os.Stderr,s);os.Exit(1)}
