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

add_library(pmm_sim src/sim/exchange_simulator.cpp src/sim/durable_store.cpp)
target_compile_features(pmm_sim PUBLIC cxx_std_20)
target_include_directories(
  pmm_sim
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_sim PUBLIC pmm_book)
pmm_enable_warnings(pmm_sim)

add_library(pmm_agents src/agents/baseline_agents.cpp)
target_compile_features(pmm_agents PUBLIC cxx_std_20)
target_include_directories(
  pmm_agents
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_agents PUBLIC pmm_sim)
pmm_enable_warnings(pmm_agents)

add_library(pmm_risk src/risk/account_risk.cpp)
target_compile_features(pmm_risk PUBLIC cxx_std_20)
target_include_directories(
  pmm_risk
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_risk PUBLIC pmm_sim)
pmm_enable_warnings(pmm_risk)

# A deliberately small line-oriented adapter for research orchestration.  It exercises the
# production AccountRiskProjection without making historical Level-2 data exchange input.
add_executable(pmm_risk_oracle src/risk/risk_oracle_main.cpp)
target_compile_features(pmm_risk_oracle PRIVATE cxx_std_20)
target_link_libraries(pmm_risk_oracle PRIVATE pmm_risk)
pmm_enable_warnings(pmm_risk_oracle)
# The research runner reads this generated path instead of embedding a generator- or
# machine-specific executable path in an experiment configuration.
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/pmm_risk_oracle.path"
     CONTENT "$<TARGET_FILE:pmm_risk_oracle>")

add_library(pmm_market_maker src/market_maker/market_maker.cpp)
target_compile_features(pmm_market_maker PUBLIC cxx_std_20)
target_include_directories(
  pmm_market_maker
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_market_maker PUBLIC pmm_risk)
pmm_enable_warnings(pmm_market_maker)

add_executable(pmm_demo src/main.cpp)
target_compile_features(pmm_demo PRIVATE cxx_std_20)
target_include_directories(
  pmm_demo
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(pmm_demo PRIVATE pmm_market_maker)
pmm_enable_warnings(pmm_demo)
