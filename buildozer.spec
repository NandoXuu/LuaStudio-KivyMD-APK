[app]

title = LuaStudio

package.name = luastudio
package.domain = com.nandox

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf,lua,glsl,mtl,obj,glb,lsa,lpkg,txt,md,json,xml,sh,c,h,s,ld

source.exclude_dirs = tests,__pycache__,.git,bin,.buildozer

version = 7.0

requirements = python3,kivy==2.3.1,kivymd,pillow,numpy,plyer,pyjnius,pygame,pygments,fonttools,gtts

orientation = landscape

fullscreen = 0

icon.filename = assets/luastudio_icon.png

presplash.filename = assets/luastudio_presplash.png

android.permissions = INTERNET,VIBRATE,CAMERA,RECORD_AUDIO

android.api = 35
android.minapi = 23
android.ndk = 28c

android.accept_sdk_license = True

android.archs = arm64-v8a

android.allow_backup = False

p4a.bootstrap = sdl2

[buildozer]

log_level = 2
