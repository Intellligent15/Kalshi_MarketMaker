include(${PROJECT_SOURCE_DIR}/cmake/Warnings.cmake)

add_library(
  pmm_core
  src/core/execution.cpp
  src/core/inventory.cpp
  src/core/market.cpp
  src/core/order.cpp
  src/core/primitives.cpp)
target_compile_features(pmm_core PUBLIC cxx_std_20)
target_include_directories(
  pmm_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
pmm_enable_warnings(pmm_core)

add_library(pmm_book src/book/order_book.cpp)
target_compile_features(pmm_book PUBLIC cxx_std_20)
target_include_directories(
  pmm_book
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_book PUBLIC pmm_core)
pmm_enable_warnings(pmm_book)

add_executable(pmm_demo src/main.cpp)
target_compile_features(pmm_demo PRIVATE cxx_std_20)
target_include_directories(
  pmm_demo
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_demo PRIVATE pmm_core)
pmm_enable_warnings(pmm_demo)
