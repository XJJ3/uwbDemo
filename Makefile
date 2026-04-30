# 延迟测试 C++ 项目 Makefile
# 直接在 uwbDemo 目录下编译，不需要 cmake

CXX = g++
CXXFLAGS = -std=c++11 -O2 -Wall
SERIAL_DIR = ../Nooploop/serial
INCLUDES = -I$(SERIAL_DIR)/include

SERIAL_SRCS = $(SERIAL_DIR)/src/serial.cc $(SERIAL_DIR)/src/impl/unix.cc
SERIAL_OBJS = $(SERIAL_SRCS:.cc=.o)

TARGETS = latency_master latency_slave

.PHONY: all clean

all: $(TARGETS)

# 编译 serial 库的目标文件
%.o: %.cc
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@

latency_master: latency_master.cpp $(SERIAL_OBJS)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $^

latency_slave: latency_slave.cpp $(SERIAL_OBJS)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $^

clean:
	rm -f $(TARGETS) $(SERIAL_OBJS)
