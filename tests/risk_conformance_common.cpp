#include "risk_conformance_common.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <charconv>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <type_traits>
#include <utility>

namespace pmm::risk_conformance {
namespace {

using Path = std::filesystem::path;

class Sha256 final {
 public:
  [[nodiscard]] static std::string Hex(std::string_view input) {
    Sha256 hash;
    for (const char value : input) {
      hash.Update(static_cast<unsigned char>(value));
    }
    return hash.Finish();
  }

 private:
  static constexpr std::array<std::uint32_t, 64> kRoundConstants{
      0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U, 0x923f82a4U,
      0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U, 0x72be5d74U, 0x80deb1feU,
      0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU,
      0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU, 0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
      0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU,
      0x53380d13U, 0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
      0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U, 0x19a4c116U,
      0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
      0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U, 0x90befffaU, 0xa4506cebU, 0xbef9a3f7U,
      0xc67178f2U};

  [[nodiscard]] static constexpr std::uint32_t RotateRight(std::uint32_t value,
                                                           std::uint32_t count) {
    return (value >> count) | (value << (32U - count));
  }

  void Update(unsigned char value) {
    buffer_[buffer_size_++] = value;
    bit_count_ += 8U;
    if (buffer_size_ == buffer_.size()) {
      Transform();
      buffer_size_ = 0;
    }
  }

  [[nodiscard]] std::string Finish() {
    const std::uint64_t original_bit_count = bit_count_;
    Update(0x80U);
    while (buffer_size_ != 56U) {
      Update(0U);
    }
    for (int shift = 56; shift >= 0; shift -= 8) {
      const auto byte = static_cast<unsigned char>((original_bit_count >> shift) & 0xffU);
      Update(byte);
    }

    static constexpr char kHex[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (const std::uint32_t word : state_) {
      for (int shift = 28; shift >= 0; shift -= 4) {
        result.push_back(kHex[(word >> shift) & 0x0fU]);
      }
    }
    return result;
  }

  void Transform() {
    std::array<std::uint32_t, 64> words{};
    for (std::size_t index = 0; index < 16; ++index) {
      const std::size_t offset = index * 4U;
      words[index] = (static_cast<std::uint32_t>(buffer_[offset]) << 24U) |
                     (static_cast<std::uint32_t>(buffer_[offset + 1U]) << 16U) |
                     (static_cast<std::uint32_t>(buffer_[offset + 2U]) << 8U) |
                     static_cast<std::uint32_t>(buffer_[offset + 3U]);
    }
    for (std::size_t index = 16; index < words.size(); ++index) {
      const std::uint32_t small_sigma0 = RotateRight(words[index - 15U], 7U) ^
                                         RotateRight(words[index - 15U], 18U) ^
                                         (words[index - 15U] >> 3U);
      const std::uint32_t small_sigma1 = RotateRight(words[index - 2U], 17U) ^
                                         RotateRight(words[index - 2U], 19U) ^
                                         (words[index - 2U] >> 10U);
      words[index] = words[index - 16U] + small_sigma0 + words[index - 7U] + small_sigma1;
    }

    std::uint32_t a = state_[0];
    std::uint32_t b = state_[1];
    std::uint32_t c = state_[2];
    std::uint32_t d = state_[3];
    std::uint32_t e = state_[4];
    std::uint32_t f = state_[5];
    std::uint32_t g = state_[6];
    std::uint32_t h = state_[7];
    for (std::size_t index = 0; index < words.size(); ++index) {
      const std::uint32_t big_sigma1 =
          RotateRight(e, 6U) ^ RotateRight(e, 11U) ^ RotateRight(e, 25U);
      const std::uint32_t choose = (e & f) ^ ((~e) & g);
      const std::uint32_t temporary1 =
          h + big_sigma1 + choose + kRoundConstants[index] + words[index];
      const std::uint32_t big_sigma0 =
          RotateRight(a, 2U) ^ RotateRight(a, 13U) ^ RotateRight(a, 22U);
      const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
      const std::uint32_t temporary2 = big_sigma0 + majority;
      h = g;
      g = f;
      f = e;
      e = d + temporary1;
      d = c;
      c = b;
      b = a;
      a = temporary1 + temporary2;
    }
    state_[0] += a;
    state_[1] += b;
    state_[2] += c;
    state_[3] += d;
    state_[4] += e;
    state_[5] += f;
    state_[6] += g;
    state_[7] += h;
  }

  std::array<unsigned char, 64> buffer_{};
  std::size_t buffer_size_ = 0;
  std::uint64_t bit_count_ = 0;
  std::array<std::uint32_t, 8> state_{0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
                                      0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U};
};

[[nodiscard]] bool IsSafeMemberName(const std::string& name) {
  const Path member(name);
  return !name.empty() && member == member.filename() && !member.is_absolute() && name != "." &&
         name != ".." && name.find('\\') == std::string::npos;
}

}  // namespace

void Fail(const std::string& location, const std::string& message) {
  throw std::runtime_error(location + ": " + message);
}

std::string Sha256Hex(std::string_view input) {
  return Sha256::Hex(input);
}

std::string ReadFile(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    Fail(path.string(), "cannot open file");
  }
  std::ostringstream contents;
  contents << input.rdbuf();
  if (!input.good() && !input.eof()) {
    Fail(path.string(), "cannot read file");
  }
  return contents.str();
}

Json ReadCanonicalJson(const std::filesystem::path& path) {
  const std::string bytes = ReadFile(path);
  if (bytes.starts_with("\xEF\xBB\xBF")) {
    Fail(path.string(), "must not contain a UTF-8 byte-order mark");
  }
  Json document;
  try {
    document = Json::parse(bytes);
  } catch (const Json::parse_error& error) {
    Fail(path.string(), std::string("invalid JSON: ") + error.what());
  }
  if (CanonicalDump(document) != bytes) {
    Fail(path.string(), "must be canonical sorted-key JSON with exactly one final LF");
  }
  return document;
}

std::string CanonicalDump(const Json& document) {
  return document.dump() + "\n";
}

void CheckKeys(const Json& value, const std::set<std::string>& required,
               const std::set<std::string>& optional, const std::string& location) {
  if (!value.is_object()) {
    Fail(location, "must be an object");
  }
  for (const auto& [key, ignored] : value.items()) {
    static_cast<void>(ignored);
    if (!required.contains(key) && !optional.contains(key)) {
      Fail(location, "has unknown field '" + key + "'");
    }
  }
  for (const std::string& key : required) {
    if (!value.contains(key)) {
      Fail(location, "is missing required field '" + key + "'");
    }
  }
}

std::string StringField(const Json& value, const char* key, const std::string& location) {
  const Json& field = value.at(key);
  if (!field.is_string()) {
    Fail(location + "." + key, "must be a string");
  }
  return field.get<std::string>();
}

std::uint64_t UnsignedDecimal(const Json& value, const char* key, const std::string& location) {
  const std::string text = StringField(value, key, location);
  if (text.empty() || (text.size() > 1U && text.front() == '0') ||
      !std::all_of(text.begin(), text.end(),
                   [](unsigned char character) { return std::isdigit(character) != 0; })) {
    Fail(location + "." + key, "must be a canonical unsigned decimal string");
  }
  std::uint64_t parsed = 0;
  const auto [position, error] = std::from_chars(text.data(), text.data() + text.size(), parsed);
  if (error != std::errc{} || position != text.data() + text.size()) {
    Fail(location + "." + key, "is outside unsigned 64-bit range");
  }
  return parsed;
}

std::int64_t NonnegativeInt64(const Json& value, const char* key, const std::string& location) {
  const std::uint64_t parsed = UnsignedDecimal(value, key, location);
  if (parsed > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    Fail(location + "." + key, "is outside signed 64-bit range");
  }
  return static_cast<std::int64_t>(parsed);
}

std::int64_t SignedDecimal(const Json& value, const char* key, const std::string& location) {
  const std::string text = StringField(value, key, location);
  const std::string_view digits = !text.empty() && text.front() == '-'
                                      ? std::string_view(text).substr(1U)
                                      : std::string_view(text);
  if (digits.empty() || (digits.size() > 1U && digits.front() == '0') || text == "-0" ||
      !std::all_of(digits.begin(), digits.end(),
                   [](unsigned char character) { return std::isdigit(character) != 0; })) {
    Fail(location + "." + key, "must be a canonical signed decimal string");
  }
  std::int64_t parsed = 0;
  const auto [position, error] = std::from_chars(text.data(), text.data() + text.size(), parsed);
  if (error != std::errc{} || position != text.data() + text.size()) {
    Fail(location + "." + key, "is outside signed 64-bit range");
  }
  return parsed;
}

core::Side SideField(const Json& value, const char* key, const std::string& location) {
  const std::string side = StringField(value, key, location);
  if (side == "buy") {
    return core::Side::Buy;
  }
  if (side == "sell") {
    return core::Side::Sell;
  }
  Fail(location + "." + key, "must be 'buy' or 'sell'");
}

void RequirePositive(std::uint64_t value, const std::string& location) {
  if (value == 0) {
    Fail(location, "must be greater than zero");
  }
}

std::filesystem::path MemberPath(const std::filesystem::path& root, const std::string& name,
                                 const std::string& location) {
  if (!IsSafeMemberName(name)) {
    Fail(location, "must be a bare filename inside the fixture root");
  }
  const Path candidate = root / name;
  const auto status = std::filesystem::symlink_status(candidate);
  if (std::filesystem::is_symlink(status) || !std::filesystem::is_regular_file(status)) {
    Fail(location, "must name a regular non-symlink file");
  }
  return candidate;
}

void CheckHash(const std::string& expected, const std::string& bytes, const std::string& location) {
  if (expected.size() != 64U ||
      !std::all_of(expected.begin(), expected.end(), [](unsigned char character) {
        return (character >= '0' && character <= '9') || (character >= 'a' && character <= 'f');
      })) {
    Fail(location, "must be a lowercase SHA-256 digest");
  }
  if (Sha256Hex(bytes) != expected) {
    Fail(location, "does not match file bytes");
  }
}

Limits ParseLimits(const Json& fixture, const std::string& location) {
  Limits limits;
  if (!fixture.contains("limits")) {
    return limits;
  }
  const Json& object = fixture.at("limits");
  CheckKeys(object, {},
            {"maximum_order_quantity_contracts", "maximum_absolute_position_contracts",
             "maximum_buy_exposure_contracts", "maximum_sell_exposure_contracts",
             "maximum_pending_exposure_contracts", "maximum_active_orders"},
            location + ".limits");
  const auto read_limit = [&object, &location](const char* key, std::int64_t* destination) {
    if (object.contains(key)) {
      *destination = NonnegativeInt64(object, key, location + ".limits");
      if (*destination == 0) {
        Fail(location + ".limits." + key, "must be positive");
      }
    }
  };
  read_limit("maximum_order_quantity_contracts", &limits.maximum_order_quantity);
  read_limit("maximum_absolute_position_contracts", &limits.maximum_absolute_position);
  read_limit("maximum_buy_exposure_contracts", &limits.maximum_buy_exposure);
  read_limit("maximum_sell_exposure_contracts", &limits.maximum_sell_exposure);
  read_limit("maximum_pending_exposure_contracts", &limits.maximum_pending_exposure);
  if (object.contains("maximum_active_orders")) {
    const Json& active = object.at("maximum_active_orders");
    if (!active.is_number_unsigned()) {
      Fail(location + ".limits.maximum_active_orders", "must be an unsigned JSON integer");
    }
    const auto parsed = active.get<std::uint64_t>();
    if (parsed == 0 || parsed > std::numeric_limits<std::size_t>::max()) {
      Fail(location + ".limits.maximum_active_orders", "must be a positive size_t value");
    }
    limits.maximum_active_orders = static_cast<std::size_t>(parsed);
  }
  return limits;
}

Operation ParseOperation(const Json& operation, const std::string& location) {
  if (!operation.is_object() || !operation.contains("operation")) {
    Fail(location, "must be an operation object with an operation field");
  }
  const std::string kind = StringField(operation, "operation", location);
  if (kind == "admit") {
    CheckKeys(operation,
              {"operation", "client_intent_id", "contract_id", "side", "quantity_contracts",
               "limit_price_cents"},
              {}, location);
    const std::uint64_t client = UnsignedDecimal(operation, "client_intent_id", location);
    const std::uint64_t contract = UnsignedDecimal(operation, "contract_id", location);
    RequirePositive(client, location + ".client_intent_id");
    RequirePositive(contract, location + ".contract_id");
    return AdmitOperation{client, contract, SideField(operation, "side", location),
                          NonnegativeInt64(operation, "quantity_contracts", location),
                          NonnegativeInt64(operation, "limit_price_cents", location)};
  }
  if (kind == "bind_ingress") {
    CheckKeys(operation, {"operation", "client_intent_id", "ingress_sequence"}, {}, location);
    const std::uint64_t client = UnsignedDecimal(operation, "client_intent_id", location);
    RequirePositive(client, location + ".client_intent_id");
    return BindIngressOperation{client, UnsignedDecimal(operation, "ingress_sequence", location)};
  }
  if (kind == "acknowledge") {
    CheckKeys(operation,
              {"operation", "sequence", "ingress_sequence", "order_id", "side",
               "quantity_contracts", "limit_price_cents", "time_utc_ns"},
              {}, location);
    const std::uint64_t sequence = UnsignedDecimal(operation, "sequence", location);
    const std::uint64_t order = UnsignedDecimal(operation, "order_id", location);
    RequirePositive(sequence, location + ".sequence");
    RequirePositive(order, location + ".order_id");
    return AcknowledgeOperation{sequence,
                                UnsignedDecimal(operation, "ingress_sequence", location),
                                order,
                                SideField(operation, "side", location),
                                NonnegativeInt64(operation, "quantity_contracts", location),
                                NonnegativeInt64(operation, "limit_price_cents", location),
                                SignedDecimal(operation, "time_utc_ns", location)};
  }
  if (kind == "fill") {
    CheckKeys(operation,
              {"operation", "sequence", "order_id", "side", "quantity_contracts", "time_utc_ns"},
              {}, location);
    const std::uint64_t sequence = UnsignedDecimal(operation, "sequence", location);
    const std::uint64_t order = UnsignedDecimal(operation, "order_id", location);
    RequirePositive(sequence, location + ".sequence");
    RequirePositive(order, location + ".order_id");
    return FillOperation{sequence, order, SideField(operation, "side", location),
                         NonnegativeInt64(operation, "quantity_contracts", location),
                         SignedDecimal(operation, "time_utc_ns", location)};
  }
  if (kind == "cancel" || kind == "logical_expiry") {
    CheckKeys(operation, {"operation", "sequence", "order_id", "time_utc_ns"}, {}, location);
    const std::uint64_t sequence = UnsignedDecimal(operation, "sequence", location);
    const std::uint64_t order = UnsignedDecimal(operation, "order_id", location);
    RequirePositive(sequence, location + ".sequence");
    RequirePositive(order, location + ".order_id");
    return CancelOperation{sequence, order, SignedDecimal(operation, "time_utc_ns", location)};
  }
  if (kind == "command_rejected") {
    CheckKeys(operation, {"operation", "sequence", "ingress_sequence", "time_utc_ns"}, {},
              location);
    const std::uint64_t sequence = UnsignedDecimal(operation, "sequence", location);
    RequirePositive(sequence, location + ".sequence");
    return CommandRejectedOperation{sequence,
                                    UnsignedDecimal(operation, "ingress_sequence", location),
                                    SignedDecimal(operation, "time_utc_ns", location)};
  }
  if (kind == "kill_switch") {
    CheckKeys(operation, {"operation", "active"}, {}, location);
    if (!operation.at("active").is_boolean()) {
      Fail(location + ".active", "must be a boolean");
    }
    return KillSwitchOperation{operation.at("active").get<bool>()};
  }
  Fail(location + ".operation", "is not a supported lifecycle operation");
}

ExpectedState ParseState(const Json& state, const std::string& location) {
  CheckKeys(state,
            {"event_watermark", "kill_switch_active", "live_orders", "net_position_contracts",
             "open_buy_contracts", "open_sell_contracts", "pending_buy_contracts", "pending_orders",
             "pending_sell_contracts"},
            {}, location);
  if (!state.at("kill_switch_active").is_boolean() || !state.at("live_orders").is_array() ||
      !state.at("pending_orders").is_array()) {
    Fail(location, "has invalid state container types");
  }
  ExpectedState parsed{UnsignedDecimal(state, "event_watermark", location),
                       SignedDecimal(state, "net_position_contracts", location),
                       NonnegativeInt64(state, "open_buy_contracts", location),
                       NonnegativeInt64(state, "open_sell_contracts", location),
                       NonnegativeInt64(state, "pending_buy_contracts", location),
                       NonnegativeInt64(state, "pending_sell_contracts", location),
                       state.at("kill_switch_active").get<bool>(),
                       {},
                       {}};
  std::int64_t open_buy = 0;
  std::int64_t open_sell = 0;
  std::uint64_t prior_order = 0;
  for (std::size_t index = 0; index < state.at("live_orders").size(); ++index) {
    const Json& order = state.at("live_orders").at(index);
    const std::string item_location = location + ".live_orders[" + std::to_string(index) + "]";
    CheckKeys(order,
              {"acknowledged_at_utc_ns", "limit_price_cents", "order_id",
               "remaining_quantity_contracts", "side"},
              {}, item_location);
    const std::uint64_t order_id = UnsignedDecimal(order, "order_id", item_location);
    RequirePositive(order_id, item_location + ".order_id");
    if (index != 0 && order_id <= prior_order) {
      Fail(item_location + ".order_id", "must be strictly identifier-sorted");
    }
    prior_order = order_id;
    const core::Side side = SideField(order, "side", item_location);
    const std::int64_t quantity =
        NonnegativeInt64(order, "remaining_quantity_contracts", item_location);
    if (quantity == 0) {
      Fail(item_location + ".remaining_quantity_contracts", "must be positive for a live order");
    }
    (side == core::Side::Buy ? open_buy : open_sell) += quantity;
    parsed.live_orders.push_back(ExpectedLiveOrder{
        order_id, side, NonnegativeInt64(order, "limit_price_cents", item_location), quantity,
        SignedDecimal(order, "acknowledged_at_utc_ns", item_location)});
  }
  std::int64_t pending_buy = 0;
  std::int64_t pending_sell = 0;
  std::uint64_t prior_client = 0;
  for (std::size_t index = 0; index < state.at("pending_orders").size(); ++index) {
    const Json& order = state.at("pending_orders").at(index);
    const std::string item_location = location + ".pending_orders[" + std::to_string(index) + "]";
    CheckKeys(order,
              {"client_intent_id", "contract_id", "ingress_sequence", "limit_price_cents",
               "post_only", "quantity_contracts", "side"},
              {}, item_location);
    const std::uint64_t client = UnsignedDecimal(order, "client_intent_id", item_location);
    const std::uint64_t contract = UnsignedDecimal(order, "contract_id", item_location);
    RequirePositive(client, item_location + ".client_intent_id");
    RequirePositive(contract, item_location + ".contract_id");
    if (index != 0 && client <= prior_client) {
      Fail(item_location + ".client_intent_id", "must be strictly identifier-sorted");
    }
    prior_client = client;
    if (!order.at("post_only").is_boolean() || !order.at("post_only").get<bool>()) {
      Fail(item_location + ".post_only", "must be true for an expected reservation");
    }
    std::optional<std::uint64_t> ingress;
    if (!order.at("ingress_sequence").is_null()) {
      ingress = UnsignedDecimal(order, "ingress_sequence", item_location);
    }
    const core::Side side = SideField(order, "side", item_location);
    const std::int64_t quantity = NonnegativeInt64(order, "quantity_contracts", item_location);
    if (quantity == 0) {
      Fail(item_location + ".quantity_contracts", "must be positive for a pending order");
    }
    (side == core::Side::Buy ? pending_buy : pending_sell) += quantity;
    parsed.pending_orders.push_back(ExpectedPendingOrder{
        client, contract, ingress, side,
        NonnegativeInt64(order, "limit_price_cents", item_location), quantity});
  }
  if (open_buy != parsed.open_buy_quantity || open_sell != parsed.open_sell_quantity ||
      pending_buy != parsed.pending_buy_quantity || pending_sell != parsed.pending_sell_quantity) {
    Fail(location, "aggregate quantities do not match order records");
  }
  return parsed;
}

std::string OperationName(const Operation& operation) {
  return std::visit(
      [](const auto& value) -> std::string {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, AdmitOperation>) {
          return "admit";
        } else if constexpr (std::is_same_v<T, BindIngressOperation>) {
          return "bind_ingress";
        } else if constexpr (std::is_same_v<T, AcknowledgeOperation>) {
          return "acknowledge";
        } else if constexpr (std::is_same_v<T, FillOperation>) {
          return "fill";
        } else if constexpr (std::is_same_v<T, CancelOperation>) {
          return "cancel_or_logical_expiry";
        } else if constexpr (std::is_same_v<T, CommandRejectedOperation>) {
          return "command_rejected";
        } else {
          return "kill_switch";
        }
      },
      operation);
}

const std::set<std::string>& LifecycleResults() {
  static const std::set<std::string> kResults{"active_order_limit",
                                              "applied",
                                              "approved",
                                              "buy_exposure_limit",
                                              "contract_mismatch",
                                              "domain_error",
                                              "duplicate_client_intent",
                                              "kill_switch_active",
                                              "order_quantity_limit",
                                              "pending_exposure_limit",
                                              "position_limit",
                                              "sell_exposure_limit"};
  return kResults;
}

std::vector<ManifestEntry> LoadManifestEntries(const std::filesystem::path& root,
                                               const std::string& manifest_schema) {
  const Path manifest_path = root / "manifest.json";
  const Json manifest = ReadCanonicalJson(manifest_path);
  CheckKeys(manifest, {"payload", "payload_sha256", "schema"}, {}, manifest_path.string());
  if (StringField(manifest, "schema", manifest_path.string()) != manifest_schema ||
      !manifest.at("payload").is_object()) {
    Fail(manifest_path.string(), "has an invalid manifest schema or payload");
  }
  const std::string payload_hash = StringField(manifest, "payload_sha256", manifest_path.string());
  CheckHash(payload_hash, CanonicalDump(manifest.at("payload")),
            manifest_path.string() + ".payload_sha256");
  const Json& payload = manifest.at("payload");
  CheckKeys(payload, {"entries", "schema"}, {}, manifest_path.string() + ".payload");
  if (StringField(payload, "schema", manifest_path.string() + ".payload") != manifest_schema ||
      !payload.at("entries").is_array() || payload.at("entries").empty()) {
    Fail(manifest_path.string() + ".payload", "has an invalid entries field");
  }
  std::vector<ManifestEntry> entries;
  std::set<std::string> expected_members{"manifest.json"};
  std::string prior_fixture_name;
  for (std::size_t index = 0; index < payload.at("entries").size(); ++index) {
    const Json& entry = payload.at("entries").at(index);
    const std::string location =
        manifest_path.string() + ".payload.entries[" + std::to_string(index) + "]";
    CheckKeys(entry, {"expected_trace", "expected_trace_sha256", "fixture", "fixture_sha256"}, {},
              location);
    const std::string fixture_name = StringField(entry, "fixture", location);
    const std::string trace_name = StringField(entry, "expected_trace", location);
    if (!prior_fixture_name.empty() && fixture_name <= prior_fixture_name) {
      Fail(location + ".fixture", "entries must be strictly fixture-name sorted");
    }
    prior_fixture_name = fixture_name;
    if (!expected_members.insert(fixture_name).second ||
        !expected_members.insert(trace_name).second) {
      Fail(location, "must not reference a duplicate member");
    }
    const Path fixture_path = MemberPath(root, fixture_name, location + ".fixture");
    const Path trace_path = MemberPath(root, trace_name, location + ".expected_trace");
    const std::string fixture_bytes = ReadFile(fixture_path);
    const std::string trace_bytes = ReadFile(trace_path);
    const Json fixture_document = ReadCanonicalJson(fixture_path);
    const Json trace_document = ReadCanonicalJson(trace_path);
    CheckHash(StringField(entry, "fixture_sha256", location), fixture_bytes,
              location + ".fixture_sha256");
    CheckHash(StringField(entry, "expected_trace_sha256", location), trace_bytes,
              location + ".expected_trace_sha256");
    entries.push_back(ManifestEntry{fixture_name, trace_name, fixture_document, trace_document});
  }
  for (const auto& entry : std::filesystem::directory_iterator(root)) {
    if (entry.is_regular_file() && entry.path().extension() == ".json" &&
        !expected_members.contains(entry.path().filename().string())) {
      Fail(entry.path().string(), "is an unreferenced fixture JSON document");
    }
  }
  return entries;
}

}  // namespace pmm::risk_conformance
