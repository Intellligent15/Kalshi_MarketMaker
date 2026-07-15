#include "risk_conformance_fixture.hpp"

#include <gtest/gtest.h>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>

#include "pmm/risk/account_risk.hpp"
#include "risk_conformance_executor.hpp"

namespace pmm::risk_conformance {
namespace {

template <typename T>
T Require(core::Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

TEST(RiskConformanceFixture, VerifiesEveryCheckedInDocument) {
  EXPECT_NO_THROW({
    const std::vector<Fixture> fixtures = LoadCorpus(FixtureRoot());
    EXPECT_EQ(fixtures.size(), 16U);
  });
}

TEST(RiskConformanceFixture, RejectsTamperedNoncanonicalMember) {
  const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
  const std::filesystem::path temporary =
      std::filesystem::temp_directory_path() / ("pmm-risk-fixture-" + std::to_string(nonce));
  std::filesystem::copy(FixtureRoot(), temporary, std::filesystem::copy_options::recursive);
  const std::filesystem::path fixture = temporary / "lifecycle.json";
  {
    std::ofstream output(fixture, std::ios::app | std::ios::binary);
    ASSERT_TRUE(output.good());
    output << ' ';
  }
  EXPECT_THROW(static_cast<void>(LoadCorpus(temporary)), std::runtime_error);
  std::filesystem::remove_all(temporary);
}

TEST(RiskConformanceFixture, DirectCppMatchesEveryReviewedTransition) {
  for (const Fixture& fixture : LoadCorpus(FixtureRoot())) {
    if (!HasExecutor(fixture, "direct_cpp")) {
      continue;
    }
    SCOPED_TRACE(fixture.fixture_id);
    risk::AccountRiskProjection projection = Require(risk::AccountRiskProjection::create(
        MakeBinding(fixture.contract_id), ToRiskLimits(fixture.limits)));
    for (std::size_t index = 0; index < fixture.operations.size(); ++index) {
      SCOPED_TRACE("transition " + std::to_string(index) + " " +
                   OperationName(fixture.operations[index]));
      EXPECT_EQ(ApplyOperation(projection, fixture.operations[index]),
                fixture.transitions[index].result);
      ExpectState(projection, fixture.transitions[index].state);
    }
  }
}

}  // namespace
}  // namespace pmm::risk_conformance
