#pragma once

#include <string>

#include "pmm/risk/account_risk.hpp"
#include "risk_conformance_common.hpp"

// Test-only helpers that replay reviewed fixture operations directly against
// AccountRiskProjection and compare its complete state after every transition.
namespace pmm::risk_conformance {

[[nodiscard]] risk::AccountBinding MakeBinding(std::uint64_t contract_value);
[[nodiscard]] risk::RiskLimits ToRiskLimits(const Limits& limits);
[[nodiscard]] std::string RejectionResult(risk::AdmissionRejectCode code);
[[nodiscard]] std::string CheckpointRejectionResult(risk::CheckpointRejectCode code);
[[nodiscard]] std::string ApplyOperation(risk::AccountRiskProjection& projection,
                                         const Operation& operation);
void ExpectState(const risk::AccountRiskProjection& projection, const ExpectedState& expected);

}  // namespace pmm::risk_conformance
