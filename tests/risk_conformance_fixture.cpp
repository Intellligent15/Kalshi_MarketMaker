#include "risk_conformance_fixture.hpp"

#include <algorithm>
#include <cctype>
#include <set>
#include <string_view>

namespace pmm::risk_conformance {
namespace {

constexpr std::string_view kFixtureSchema = "pmm.risk_conformance_fixture.v1";
constexpr std::string_view kTraceSchema = "pmm.risk_conformance_expected_trace.v1";
constexpr std::string_view kManifestSchema = "pmm.risk_conformance_fixture_manifest.v1";

[[nodiscard]] std::vector<ExpectedTransition> ParseTrace(const Json& trace,
                                                         const std::string& fixture_id,
                                                         const std::string& location) {
  CheckKeys(trace, {"fixture_id", "schema", "transitions"}, {}, location);
  if (StringField(trace, "schema", location) != kTraceSchema ||
      StringField(trace, "fixture_id", location) != fixture_id ||
      !trace.at("transitions").is_array()) {
    Fail(location, "has an invalid expected-trace identity or transitions field");
  }
  std::vector<ExpectedTransition> transitions;
  for (std::size_t index = 0; index < trace.at("transitions").size(); ++index) {
    const Json& transition = trace.at("transitions").at(index);
    const std::string item_location = location + ".transitions[" + std::to_string(index) + "]";
    CheckKeys(transition, {"result", "state"}, {}, item_location);
    const std::string result = StringField(transition, "result", item_location);
    if (!LifecycleResults().contains(result)) {
      Fail(item_location + ".result", "is not a known fixture result");
    }
    transitions.push_back(
        ExpectedTransition{result, ParseState(transition.at("state"), item_location + ".state")});
  }
  return transitions;
}

[[nodiscard]] Fixture ParseFixture(const Json& document, const Json& trace,
                                   const std::string& filename,
                                   const std::string& expected_filename) {
  CheckKeys(document, {"fixture_id", "operations", "schema"},
            {"contract_id", "executors", "limits"}, filename);
  if (StringField(document, "schema", filename) != kFixtureSchema ||
      !document.at("operations").is_array()) {
    Fail(filename, "has an invalid fixture schema or operations field");
  }
  Fixture fixture{StringField(document, "fixture_id", filename),
                  1,
                  ParseLimits(document, filename),
                  {},
                  {},
                  {}};
  if (fixture.fixture_id.empty() ||
      !std::all_of(
          fixture.fixture_id.begin(), fixture.fixture_id.end(), [](unsigned char character) {
            return std::islower(character) != 0 || std::isdigit(character) != 0 || character == '_';
          })) {
    Fail(filename + ".fixture_id", "must use lowercase letters, digits, and underscores");
  }
  if (filename != fixture.fixture_id + ".json" ||
      expected_filename != fixture.fixture_id + ".expected.json") {
    Fail(filename, "member names must match the fixture identifier");
  }
  if (document.contains("contract_id")) {
    fixture.contract_id = UnsignedDecimal(document, "contract_id", filename);
    RequirePositive(fixture.contract_id, filename + ".contract_id");
  }
  static const std::set<std::string> kExecutors{"direct_cpp", "python_reference", "v1_oracle"};
  if (document.contains("executors")) {
    if (!document.at("executors").is_array() || document.at("executors").empty()) {
      Fail(filename + ".executors", "must be a non-empty executor array");
    }
    std::set<std::string> seen_executors;
    for (const Json& executor : document.at("executors")) {
      if (!executor.is_string() || !kExecutors.contains(executor.get<std::string>()) ||
          !seen_executors.insert(executor.get<std::string>()).second) {
        Fail(filename + ".executors", "must contain unique known executor names");
      }
      fixture.executors.push_back(executor.get<std::string>());
    }
  } else {
    fixture.executors = {"direct_cpp", "python_reference", "v1_oracle"};
  }
  if (document.at("operations").empty()) {
    Fail(filename + ".operations", "must not be empty");
  }
  for (std::size_t index = 0; index < document.at("operations").size(); ++index) {
    fixture.operations.push_back(
        ParseOperation(document.at("operations").at(index),
                       filename + ".operations[" + std::to_string(index) + "]"));
  }
  if (HasExecutor(fixture, "v1_oracle")) {
    for (std::size_t index = 0; index < fixture.operations.size(); ++index) {
      if (const auto* admit = std::get_if<AdmitOperation>(&fixture.operations[index]);
          admit != nullptr && admit->contract_id != fixture.contract_id) {
        Fail(filename + ".operations[" + std::to_string(index) + "]",
             "is not faithfully expressible by the frozen V1 oracle");
      }
    }
  }
  fixture.transitions = ParseTrace(trace, fixture.fixture_id, expected_filename);
  if (fixture.transitions.size() != fixture.operations.size()) {
    Fail(expected_filename, "must have one transition for every fixture operation");
  }
  return fixture;
}

}  // namespace

std::filesystem::path FixtureRoot() {
  return std::filesystem::path(PMM_SOURCE_DIR) / "python" / "tests" / "fixtures" /
         "risk_conformance" / "v1";
}

std::vector<Fixture> LoadCorpus(const std::filesystem::path& root) {
  std::vector<Fixture> fixtures;
  for (const ManifestEntry& entry : LoadManifestEntries(root, std::string(kManifestSchema))) {
    fixtures.push_back(ParseFixture(entry.fixture_document, entry.trace_document,
                                    entry.fixture_name, entry.trace_name));
  }
  return fixtures;
}

bool HasExecutor(const Fixture& fixture, const std::string& executor) {
  return std::find(fixture.executors.begin(), fixture.executors.end(), executor) !=
         fixture.executors.end();
}

}  // namespace pmm::risk_conformance
