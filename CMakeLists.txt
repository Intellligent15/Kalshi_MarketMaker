cmake_minimum_required(VERSION 3.24)

project(
  prediction_market_ml_market_maker
  VERSION 0.1.0
  DESCRIPTION "Prediction-market simulation and market-making research platform"
  LANGUAGES CXX)

set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(PMM_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" OFF)

include(CTest)

add_subdirectory(cpp)

if(BUILD_TESTING)
  include(FetchContent)

  # Pin to an immutable upstream commit for repeatable test builds. This is only
  # fetched when tests are enabled; no third-party source is committed here.
  FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG f8d7d77c06936315286eb55f8de22cd23c188571
    GIT_SHALLOW FALSE
    SYSTEM)
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  add_subdirectory(tests)
endif()
