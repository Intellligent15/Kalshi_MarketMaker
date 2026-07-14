include(${PROJECT_SOURCE_DIR}/cmake/Warnings.cmake)

add_executable(pmm_smoke_test smoke_test.cpp)
target_compile_features(pmm_smoke_test PRIVATE cxx_std_20)
target_link_libraries(pmm_smoke_test PRIVATE GTest::gtest_main pmm_core)
pmm_enable_warnings(pmm_smoke_test)

add_executable(pmm_core_test core_domain_test.cpp)
target_compile_features(pmm_core_test PRIVATE cxx_std_20)
target_link_libraries(pmm_core_test PRIVATE GTest::gtest_main pmm_core)
pmm_enable_warnings(pmm_core_test)

add_executable(pmm_order_book_test order_book_test.cpp)
target_compile_features(pmm_order_book_test PRIVATE cxx_std_20)
target_link_libraries(pmm_order_book_test PRIVATE GTest::gtest_main pmm_book)
pmm_enable_warnings(pmm_order_book_test)

include(GoogleTest)
gtest_discover_tests(pmm_smoke_test)
gtest_discover_tests(pmm_core_test)
gtest_discover_tests(pmm_order_book_test)
