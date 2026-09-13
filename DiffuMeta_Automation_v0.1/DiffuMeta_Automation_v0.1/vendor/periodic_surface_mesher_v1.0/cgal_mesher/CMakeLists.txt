cmake_minimum_required(VERSION 3.16)
project(periodic_surface_mesher LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CGAL REQUIRED)

add_executable(periodic_surface_mesher main.cpp)
target_link_libraries(periodic_surface_mesher PRIVATE CGAL::CGAL)
