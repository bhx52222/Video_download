import AppKit
let size=1024
let image=NSImage(size:NSSize(width:size,height:size));image.lockFocus()
let rect=NSRect(x:50,y:50,width:924,height:924)
let shape=NSBezierPath(roundedRect:rect,xRadius:220,yRadius:220)
NSColor(calibratedRed:0.11,green:0.29,blue:0.85,alpha:1).setFill();shape.fill()
let inner=NSBezierPath(roundedRect:NSRect(x:206,y:264,width:612,height:500),xRadius:75,yRadius:75)
NSColor.white.withAlphaComponent(0.15).setFill();inner.fill()
let play=NSBezierPath();play.move(to:NSPoint(x:426,y:622));play.line(to:NSPoint(x:426,y:404));play.line(to:NSPoint(x:620,y:513));play.close();NSColor.white.setFill();play.fill()
let arrow=NSBezierPath();arrow.lineWidth=34;arrow.lineCapStyle = .round;arrow.lineJoinStyle = .round
arrow.move(to:NSPoint(x:694,y:392));arrow.line(to:NSPoint(x:694,y:197));arrow.move(to:NSPoint(x:623,y:268));arrow.line(to:NSPoint(x:694,y:197));arrow.line(to:NSPoint(x:765,y:268))
NSColor(calibratedRed:0.38,green:0.91,blue:0.89,alpha:1).setStroke();arrow.stroke();image.unlockFocus()
let dir=URL(fileURLWithPath:CommandLine.arguments[1]);try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
for n in [16,32,128,256,512] {for scale in [1,2] {
 let pixels=n*scale
 let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:pixels,pixelsHigh:pixels,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
 NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:rep)
 image.draw(in:NSRect(x:0,y:0,width:pixels,height:pixels));NSGraphicsContext.restoreGraphicsState()
 let suffix=scale==2 ? "@2x" : "";try rep.representation(using:.png,properties:[:])!.write(to:dir.appendingPathComponent("icon_\(n)x\(n)\(suffix).png"))
}}
