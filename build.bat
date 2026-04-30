REM Windows 编译脚本 build.bat
REM 需要安装 MinGW-w64，g++ 在 PATH 中

if not exist bin mkdir bin

g++ -std=c++11 -O2 -Wall ^
    -I../Nooploop/serial/include ^
    -c ../Nooploop/serial/src/serial.cc ^
    -o ../Nooploop/serial/src/serial.o

g++ -std=c++11 -O2 -Wall ^
    -I../Nooploop/serial/include ^
    -c ../Nooploop/serial/src/impl/win.cc ^
    -o ../Nooploop/serial/src/impl/win.o

g++ -std=c++11 -O2 -Wall ^
    -I../Nooploop/serial/include ^
    -o bin/latency_master.exe ^
    latency_master.cpp ^
    ../Nooploop/serial/src/serial.o ^
    ../Nooploop/serial/src/impl/win.o

g++ -std=c++11 -O2 -Wall ^
    -I../Nooploop/serial/include ^
    -o bin/latency_slave.exe ^
    latency_slave.cpp ^
    ../Nooploop/serial/src/serial.o ^
    ../Nooploop/serial/src/impl/win.o

echo Build complete.
echo Usage: bin\latency_master.exe COM3
echo        bin\latency_slave.exe COM4
