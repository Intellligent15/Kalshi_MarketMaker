#pragma once

#include <filesystem>
#include <string>
#include <vector>

#include "risk_conformance_common.hpp"

namespace pmm::risk_conformance {

struct Fixture {
  std::string fixture_id;
  std::uint64_t contract_id;
  Limits limits;
  std::vector<std::string> executors;
  std::vector<Operation> operations;
  std::vector<ExpectedTransition> transitions;
};

[[nodiscard]] std::filesystem::path FixtureRoot();
[[nodiscard]] std::vector<Fixture> LoadCorpus(const std::filesystem::path& root);
[[nodiscard]] bool HasExecutor(const Fixture& fixture, const std::string& executor);

}  // namespace pmm::risk_conformance
