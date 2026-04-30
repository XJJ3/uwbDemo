// latency_master.cpp - MASTER 端延迟测试
// 发送 USER_FRAME1 给 SLAVE，接收 ACK，测量往返延迟

#include <serial/serial.h>
#include <chrono>
#include <iostream>
#include <iomanip>
#include <vector>
#include <algorithm>

const unsigned char USER_FRAME1[] = {
    0x54, 0xF1, 0xFF, 0xFF, 0xFF, 0xFF, 0x05,  // header + mark
    0x00,  // remote_role = SLAVE
    0x03,  // data_length = 3
    0x00,  // remote_id = 0
    0x11, 0x11, 0x01,  // payload
    0x6C   // checksum
};
const size_t FRAME_LEN = sizeof(USER_FRAME1);
const int TEST_COUNT = 100;

int main(int argc, char* argv[]) {
    const char* port = (argc > 1) ? argv[1] : 
#ifdef _WIN32
        "COM3";
#else
        "/dev/cu.wchusbserial585C0089431";
#endif

    serial::Serial master(port, 921600, serial::Timeout::simpleTimeout(10));
    
    if (!master.isOpen()) {
        std::cerr << "无法打开串口" << std::endl;
        return 1;
    }
    
    std::cout << "MASTER 延迟测试" << std::endl;
    std::cout << "端口: " << port << std::endl;
    std::cout << "测试次数: " << TEST_COUNT << std::endl;
    std::cout << "帧: 54F1FFFFFFFF050003001111016C\n" << std::endl;
    
    std::vector<double> delays;
    
    for (int i = 0; i < TEST_COUNT; i++) {
        master.flushInput();
        
        auto t1 = std::chrono::high_resolution_clock::now();
        master.write(USER_FRAME1, FRAME_LEN);
        
        std::string ack;
        auto t3 = t1;
        while (true) {
            size_t n = master.available();
            if (n > 0) {
                master.read(ack, n);
                t3 = std::chrono::high_resolution_clock::now();
                break;
            }
            auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::high_resolution_clock::now() - t1).count();
            if (elapsed > 50000) break; // 50ms 超时
        }
        
        auto t2 = t3;
        auto us = std::chrono::duration_cast<std::chrono::microseconds>(t2 - t1).count();
        double ms = us / 1000.0;
        
        if (!ack.empty()) {
            delays.push_back(ms);
            if (i < 5 || i >= TEST_COUNT - 3) {
                std::cout << "#" << std::setw(3) << i << " | "
                          << std::fixed << std::setprecision(2) << std::setw(6) << ms
                          << "ms | 收到 " << ack.length() << "B" << std::endl;
            }
        } else {
            std::cout << "#" << std::setw(3) << i << " | 超时" << std::endl;
        }
    }
    
    master.close();
    
    if (delays.empty()) {
        std::cout << "\n全部失败，无响应" << std::endl;
        return 1;
    }
    
    std::sort(delays.begin(), delays.end());
    double sum = 0;
    for (auto d : delays) sum += d;
    
    std::cout << "\n========== 统计 ==========" << std::endl;
    std::cout << "成功: " << delays.size() << "/" << TEST_COUNT << std::endl;
    std::cout << "最小: " << std::fixed << std::setprecision(2) << delays.front() << "ms" << std::endl;
    std::cout << "最大: " << delays.back() << "ms" << std::endl;
    std::cout << "平均: " << sum / delays.size() << "ms" << std::endl;
    std::cout << "中位数: " << delays[delays.size() / 2] << "ms" << std::endl;
    
    return 0;
}
