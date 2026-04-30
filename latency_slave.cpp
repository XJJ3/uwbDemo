// latency_slave.cpp - SLAVE 端自动回复
// 收到数据后自动回复 ACK

#include <serial/serial.h>
#include <chrono>
#include <iostream>
#include <iomanip>
#include <cstring>

int main(int argc, char* argv[]) {
    const char* port = (argc > 1) ? argv[1] : 
#ifdef _WIN32
        "COM4";
#else
        "/dev/cu.wchusbserial5AB50010561";
#endif

    serial::Serial slave(port, 921600, serial::Timeout::simpleTimeout(1));
    
    if (!slave.isOpen()) {
        std::cerr << "无法打开串口" << std::endl;
        return 1;
    }
    
    std::cout << "SLAVE 自动回复" << std::endl;
    std::cout << "端口: " << port << std::endl;
    std::cout << "按 Ctrl+C 退出\n" << std::endl;
    
    int count = 0;
    unsigned char ack[15] = {'A', 'C', 'K'};
    
    auto start = std::chrono::steady_clock::now();
    
    while (true) {
        size_t n = slave.available();
        if (n > 0) {
            unsigned char buf[256];
            slave.read(buf, n);
            
            auto now = std::chrono::steady_clock::now();
            
            // 填充序号和时间戳到 ACK
            memcpy(ack + 3, &count, 4);
            auto us = std::chrono::duration_cast<std::chrono::microseconds>(
                now - start).count();
            memcpy(ack + 7, &us, 8);
            
            slave.write(ack, 15);
            count++;
            
            if (count % 50 == 0) {
                auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                    std::chrono::steady_clock::now() - start).count();
                std::cout << "已处理: " << count << " | 速率: " 
                          << (elapsed > 0 ? count / elapsed : 0) << "/s" << std::endl;
            }
        }
    }
    
    return 0;
}
