#include "durable_store.hpp"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <string_view>
#include <utility>

namespace pmm::sim {
namespace {

constexpr std::array<std::uint8_t, 8> kJournalHeader{'P', 'M', 'M', 'J', 'N', 'L', '1', 0};
constexpr std::array<std::uint8_t, 8> kSnapshotHeader{'P', 'M', 'M', 'S', 'N', 'P', '1', 0};
constexpr std::uint32_t kVersion = 1;
constexpr std::uint32_t kFrameMagic = 0x504d4d46U;
constexpr std::size_t kFrameHeaderSize = 14;

enum class FrameType : std::uint16_t {
  Genesis = 1,
  Prepared = 2,
  Committed = 3,
};

core::DomainError Error(core::DomainErrorCode code, std::string message) {
  return core::DomainError{code, std::move(message)};
}

class Writer {
 public:
  void u8(std::uint8_t value) {
    data_.push_back(value);
  }
  void u16(std::uint16_t value) {
    for (unsigned shift = 0; shift < 16; shift += 8) {
      u8(static_cast<std::uint8_t>(value >> shift));
    }
  }
  void u32(std::uint32_t value) {
    for (unsigned shift = 0; shift < 32; shift += 8) {
      u8(static_cast<std::uint8_t>(value >> shift));
    }
  }
  void u64(std::uint64_t value) {
    for (unsigned shift = 0; shift < 64; shift += 8) {
      u8(static_cast<std::uint8_t>(value >> shift));
    }
  }
  void i64(std::int64_t value) {
    u64(static_cast<std::uint64_t>(value));
  }
  void string(std::string_view value) {
    u64(value.size());
    data_.insert(data_.end(), value.begin(), value.end());
  }
  void bytes(const std::vector<std::uint8_t>& value) {
    data_.insert(data_.end(), value.begin(), value.end());
  }
  [[nodiscard]] const std::vector<std::uint8_t>& data() const {
    return data_;
  }
  [[nodiscard]] std::vector<std::uint8_t> take() {
    return std::move(data_);
  }

 private:
  std::vector<std::uint8_t> data_;
};

class Reader {
 public:
  Reader(const std::vector<std::uint8_t>& data, std::size_t begin = 0,
         std::size_t end = std::numeric_limits<std::size_t>::max())
      : data_(data), offset_(begin), end_(std::min(end, data.size())) {}

  [[nodiscard]] core::Result<std::uint8_t> u8() {
    if (offset_ == end_) {
      return fail("unexpected end of durable data");
    }
    return data_[offset_++];
  }
  [[nodiscard]] core::Result<std::uint16_t> u16() {
    return integer<std::uint16_t, 2>();
  }
  [[nodiscard]] core::Result<std::uint32_t> u32() {
    return integer<std::uint32_t, 4>();
  }
  [[nodiscard]] core::Result<std::uint64_t> u64() {
    return integer<std::uint64_t, 8>();
  }
  [[nodiscard]] core::Result<std::int64_t> i64() {
    const auto value = u64();
    if (!value) {
      return value.error();
    }
    return static_cast<std::int64_t>(value.value());
  }
  [[nodiscard]] core::Result<std::string> string() {
    const auto size = u64();
    if (!size) {
      return size.error();
    }
    if (size.value() > end_ - offset_) {
      return fail("durable string exceeds frame boundary");
    }
    const std::size_t length = static_cast<std::size_t>(size.value());
    std::string result(data_.begin() + static_cast<std::ptrdiff_t>(offset_),
                       data_.begin() + static_cast<std::ptrdiff_t>(offset_ + length));
    offset_ += length;
    return result;
  }
  [[nodiscard]] bool done() const {
    return offset_ == end_;
  }
  [[nodiscard]] std::size_t offset() const {
    return offset_;
  }

 private:
  template <typename T, unsigned Width>
  [[nodiscard]] core::Result<T> integer() {
    if (end_ - offset_ < Width) {
      return fail("unexpected end of durable data");
    }
    T value = 0;
    for (unsigned index = 0; index < Width; ++index) {
      value |= static_cast<T>(data_[offset_++]) << (index * 8U);
    }
    return value;
  }
  [[nodiscard]] core::DomainError fail(const char* message) const {
    return Error(core::DomainErrorCode::CorruptJournal, message);
  }

  const std::vector<std::uint8_t>& data_;
  std::size_t offset_;
  std::size_t end_;
};

std::uint32_t crc32(const std::vector<std::uint8_t>& data) {
  std::uint32_t result = 0xffffffffU;
  for (const std::uint8_t byte : data) {
    result ^= byte;
    for (unsigned bit = 0; bit < 8; ++bit) {
      const std::uint32_t mask = 0U - (result & 1U);
      result = (result >> 1U) ^ (0xedb88320U & mask);
    }
  }
  return ~result;
}

template <typename Id>
void write_id(Writer& writer, const Id& id) {
  writer.u64(id.value());
}

template <typename Id>
core::Result<Id> read_id(Reader& reader) {
  const auto value = reader.u64();
  if (!value) {
    return value.error();
  }
  return Id::from_value(value.value());
}

void write_price(Writer& writer, core::Price value) {
  writer.u64(value.units());
}
core::Result<core::Price> read_price(Reader& reader) {
  const auto value = reader.u64();
  if (!value ||
      value.value() > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable price is invalid");
  }
  return core::Price::from_units(static_cast<std::int64_t>(value.value()));
}
void write_quantity(Writer& writer, core::Quantity value) {
  writer.u64(value.units());
}
core::Result<core::Quantity> read_quantity(Reader& reader) {
  const auto value = reader.u64();
  if (!value ||
      value.value() > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable quantity is invalid");
  }
  return core::Quantity::from_units(static_cast<std::int64_t>(value.value()));
}
void write_timestamp(Writer& writer, core::Timestamp value) {
  writer.i64(value.unix_nanoseconds());
}
core::Result<core::Timestamp> read_timestamp(Reader& reader) {
  const auto value = reader.i64();
  if (!value) {
    return value.error();
  }
  return core::Timestamp::from_unix_nanoseconds(value.value());
}

void write_contract(Writer& writer, const core::Contract& contract) {
  write_id(writer, contract.id());
  write_id(writer, contract.market_id());
  write_price(writer, contract.payout());
  write_price(writer, contract.price_grid().minimum());
  write_price(writer, contract.price_grid().maximum());
  write_price(writer, contract.price_grid().increment());
  writer.u64(contract.lot_size().units());
}

core::Result<core::Contract> read_contract(Reader& reader) {
  const auto id = read_id<core::ContractId>(reader);
  const auto market_id = read_id<core::MarketId>(reader);
  const auto payout = read_price(reader);
  const auto minimum = read_price(reader);
  const auto maximum = read_price(reader);
  const auto increment = read_price(reader);
  const auto lot = reader.u64();
  if (!id || !market_id || !payout || !minimum || !maximum || !increment || !lot ||
      lot.value() > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable contract is invalid");
  }
  const auto grid = core::PriceGrid::create(minimum.value(), maximum.value(), increment.value());
  const auto lot_size = core::LotSize::from_units(static_cast<std::int64_t>(lot.value()));
  if (!grid || !lot_size) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable contract rules are invalid");
  }
  return core::Contract::create(id.value(), market_id.value(), payout.value(), grid.value(),
                                lot_size.value());
}

void write_market(Writer& writer, const core::Market& market) {
  write_id(writer, market.id());
  writer.string(market.title());
  writer.u8(static_cast<std::uint8_t>(market.status()));
  write_contract(writer, market.contract());
}

core::Result<core::Market> read_market(Reader& reader) {
  const auto id = read_id<core::MarketId>(reader);
  const auto title = reader.string();
  const auto status = reader.u8();
  const auto contract = read_contract(reader);
  if (!id || !title || !status || !contract ||
      status.value() > static_cast<std::uint8_t>(core::MarketStatus::Settled)) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable market is invalid");
  }
  return core::Market::create(id.value(), title.value(), contract.value(),
                              static_cast<core::MarketStatus>(status.value()));
}

void write_order(Writer& writer, const core::Order& order) {
  write_id(writer, order.id());
  write_id(writer, order.trader_id());
  write_id(writer, order.contract_id());
  writer.u8(static_cast<std::uint8_t>(order.side()));
  writer.u8(static_cast<std::uint8_t>(order.type()));
  write_quantity(writer, order.quantity());
  writer.u8(order.limit_price().has_value() ? 1U : 0U);
  if (order.limit_price().has_value()) {
    write_price(writer, *order.limit_price());
  }
  write_timestamp(writer, order.submitted_at());
}

const core::Contract* contract_for(const std::vector<core::Market>& markets, core::ContractId id) {
  for (const core::Market& market : markets) {
    if (market.contract().id() == id) {
      return &market.contract();
    }
  }
  return nullptr;
}

core::Result<core::Order> read_order(Reader& reader, const std::vector<core::Market>& markets) {
  const auto id = read_id<core::OrderId>(reader);
  const auto trader = read_id<core::TraderId>(reader);
  const auto contract_id = read_id<core::ContractId>(reader);
  const auto side = reader.u8();
  const auto type = reader.u8();
  const auto quantity = read_quantity(reader);
  const auto has_limit = reader.u8();
  if (!id || !trader || !contract_id || !side || !type || !quantity || !has_limit ||
      side.value() > static_cast<std::uint8_t>(core::Side::Sell) ||
      type.value() > static_cast<std::uint8_t>(core::OrderType::Market) || has_limit.value() > 1U) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable order is invalid");
  }
  std::optional<core::Price> limit;
  if (has_limit.value() == 1U) {
    const auto price = read_price(reader);
    if (!price) {
      return price.error();
    }
    limit = price.value();
  }
  const auto submitted_at = read_timestamp(reader);
  if (!submitted_at) {
    return submitted_at.error();
  }
  const core::Contract* contract = contract_for(markets, contract_id.value());
  if (contract == nullptr) {
    return Error(core::DomainErrorCode::CorruptJournal,
                 "durable order references an unknown contract");
  }
  if (type.value() == static_cast<std::uint8_t>(core::OrderType::Limit) && limit.has_value()) {
    return core::Order::create_limit(id.value(), trader.value(), contract_id.value(),
                                     static_cast<core::Side>(side.value()), quantity.value(),
                                     *limit, submitted_at.value(), *contract);
  }
  if (type.value() == static_cast<std::uint8_t>(core::OrderType::Market) && !limit.has_value()) {
    return core::Order::create_market(id.value(), trader.value(), contract_id.value(),
                                      static_cast<core::Side>(side.value()), quantity.value(),
                                      submitted_at.value(), *contract);
  }
  return Error(core::DomainErrorCode::CorruptJournal,
               "durable order has an invalid type/price pair");
}

void write_trade(Writer& writer, const core::Trade& trade) {
  write_id(writer, trade.id());
  write_id(writer, trade.contract_id());
  write_id(writer, trade.buyer_order_id());
  write_id(writer, trade.seller_order_id());
  write_id(writer, trade.buyer_trader_id());
  write_id(writer, trade.seller_trader_id());
  write_price(writer, trade.price());
  write_quantity(writer, trade.quantity());
  write_timestamp(writer, trade.executed_at());
  write_id(writer, trade.sequence());
  writer.u8(trade.aggressor_side().has_value()
                ? static_cast<std::uint8_t>(*trade.aggressor_side()) + 1U
                : 0U);
}

core::Result<core::Trade> read_trade(Reader& reader, const std::vector<core::Market>& markets) {
  const auto id = read_id<core::TradeId>(reader);
  const auto contract_id = read_id<core::ContractId>(reader);
  const auto buyer_order = read_id<core::OrderId>(reader);
  const auto seller_order = read_id<core::OrderId>(reader);
  const auto buyer_trader = read_id<core::TraderId>(reader);
  const auto seller_trader = read_id<core::TraderId>(reader);
  const auto price = read_price(reader);
  const auto quantity = read_quantity(reader);
  const auto executed_at = read_timestamp(reader);
  const auto sequence = read_id<core::SequenceNumber>(reader);
  const auto aggressor = reader.u8();
  if (!id || !contract_id || !buyer_order || !seller_order || !buyer_trader || !seller_trader ||
      !price || !quantity || !executed_at || !sequence || !aggressor || aggressor.value() > 2U) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable trade is invalid");
  }
  const core::Contract* contract = contract_for(markets, contract_id.value());
  if (contract == nullptr) {
    return Error(core::DomainErrorCode::CorruptJournal,
                 "durable trade references an unknown contract");
  }
  std::optional<core::Side> aggressor_side;
  if (aggressor.value() != 0U) {
    aggressor_side = static_cast<core::Side>(aggressor.value() - 1U);
  }
  return core::Trade::create(id.value(), contract_id.value(), buyer_order.value(),
                             seller_order.value(), buyer_trader.value(), seller_trader.value(),
                             price.value(), quantity.value(), executed_at.value(), sequence.value(),
                             aggressor_side, *contract);
}

void write_update(Writer& writer, const book::OrderUpdate& update) {
  write_id(writer, update.order_id);
  writer.u8(static_cast<std::uint8_t>(update.status));
  write_quantity(writer, update.remaining_quantity);
}
core::Result<book::OrderUpdate> read_update(Reader& reader) {
  const auto id = read_id<core::OrderId>(reader);
  const auto status = reader.u8();
  const auto quantity = read_quantity(reader);
  if (!id || !status || !quantity ||
      status.value() > static_cast<std::uint8_t>(book::OrderStatus::Expired)) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable order update is invalid");
  }
  return book::OrderUpdate{id.value(), static_cast<book::OrderStatus>(status.value()),
                           quantity.value()};
}

void write_command(Writer& writer, const ExchangeCommand& command) {
  std::visit(
      [&writer](const auto& value) {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, SubmitOrderRequest>) {
          writer.u8(1U);
          write_id(writer, value.trader_id);
          write_id(writer, value.contract_id);
          writer.u8(static_cast<std::uint8_t>(value.side));
          writer.u8(static_cast<std::uint8_t>(value.type));
          write_quantity(writer, value.quantity);
          writer.u8(value.limit_price.has_value() ? 1U : 0U);
          if (value.limit_price.has_value()) write_price(writer, *value.limit_price);
          write_timestamp(writer, value.submitted_at);
          writer.u8(value.post_only ? 1U : 0U);
        } else if constexpr (std::is_same_v<T, CancelOrderRequest>) {
          writer.u8(2U);
          write_id(writer, value.trader_id);
          write_id(writer, value.contract_id);
          write_id(writer, value.order_id);
        } else {
          writer.u8(3U);
          write_id(writer, value.market_id);
          writer.u8(static_cast<std::uint8_t>(value.target_status));
        }
      },
      command);
}

core::Result<ExchangeCommand> read_command(Reader& reader) {
  const auto type = reader.u8();
  if (!type) return type.error();
  if (type.value() == 1U) {
    const auto trader = read_id<core::TraderId>(reader);
    const auto contract = read_id<core::ContractId>(reader);
    const auto side = reader.u8();
    const auto order_type = reader.u8();
    const auto quantity = read_quantity(reader);
    const auto has_limit = reader.u8();
    if (!trader || !contract || !side || !order_type || !quantity || !has_limit ||
        side.value() > 1U || order_type.value() > 1U || has_limit.value() > 1U) {
      return Error(core::DomainErrorCode::CorruptJournal, "durable submit command is invalid");
    }
    std::optional<core::Price> limit;
    if (has_limit.value() == 1U) {
      const auto price = read_price(reader);
      if (!price) return price.error();
      limit = price.value();
    }
    const auto submitted_at = read_timestamp(reader);
    const auto post_only = reader.u8();
    if (!submitted_at || !post_only || post_only.value() > 1U) {
      return Error(core::DomainErrorCode::CorruptJournal, "durable submit command is invalid");
    }
    return ExchangeCommand{
        SubmitOrderRequest{trader.value(), contract.value(), static_cast<core::Side>(side.value()),
                           static_cast<core::OrderType>(order_type.value()), quantity.value(),
                           limit, submitted_at.value(), post_only.value() == 1U}};
  }
  if (type.value() == 2U) {
    const auto trader = read_id<core::TraderId>(reader);
    const auto contract = read_id<core::ContractId>(reader);
    const auto order = read_id<core::OrderId>(reader);
    if (!trader || !contract || !order)
      return Error(core::DomainErrorCode::CorruptJournal, "durable cancel command is invalid");
    return ExchangeCommand{CancelOrderRequest{trader.value(), contract.value(), order.value()}};
  }
  if (type.value() == 3U) {
    const auto market = read_id<core::MarketId>(reader);
    const auto status = reader.u8();
    if (!market || !status ||
        status.value() > static_cast<std::uint8_t>(core::MarketStatus::Settled)) {
      return Error(core::DomainErrorCode::CorruptJournal, "durable lifecycle command is invalid");
    }
    return ExchangeCommand{
        MarketLifecycleCommand{market.value(), static_cast<core::MarketStatus>(status.value())}};
  }
  return Error(core::DomainErrorCode::CorruptJournal, "durable command type is unknown");
}

void write_scheduled(Writer& writer, const ScheduledCommand& command) {
  write_timestamp(writer, command.scheduled_at);
  writer.u64(command.ingress_sequence);
  write_command(writer, command.command);
}
core::Result<ScheduledCommand> read_scheduled(Reader& reader) {
  const auto time = read_timestamp(reader);
  const auto ingress = reader.u64();
  const auto command = read_command(reader);
  if (!time || !ingress || !command || ingress.value() == 0U) {
    return Error(core::DomainErrorCode::CorruptJournal, "durable scheduled command is invalid");
  }
  return ScheduledCommand{time.value(), ingress.value(), command.value()};
}

void write_event(Writer& writer, const ExchangeEvent& event) {
  write_id(writer, event.sequence);
  write_timestamp(writer, event.occurred_at);
  writer.u64(event.ingress_sequence);
  std::visit(
      [&writer](const auto& value) {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, OrderAcknowledged>) {
          writer.u8(1U);
          write_order(writer, value.order);
        } else if constexpr (std::is_same_v<T, TradeExecuted>) {
          writer.u8(2U);
          write_trade(writer, value.execution.trade);
        } else if constexpr (std::is_same_v<T, OrderOutcome>) {
          writer.u8(3U);
          write_update(writer, value.update);
        } else if constexpr (std::is_same_v<T, CancellationAcknowledged>) {
          writer.u8(4U);
          write_update(writer, value.update);
        } else if constexpr (std::is_same_v<T, MarketStatusChanged>) {
          writer.u8(5U);
          write_id(writer, value.market_id);
          writer.u8(static_cast<std::uint8_t>(value.previous_status));
          writer.u8(static_cast<std::uint8_t>(value.current_status));
        } else if constexpr (std::is_same_v<T, BookDepthChanged>) {
          writer.u8(6U);
          write_id(writer, value.contract_id);
          writer.u64(value.levels.size());
          for (const auto& level : value.levels) {
            writer.u8(static_cast<std::uint8_t>(level.side));
            write_price(writer, level.price);
            write_quantity(writer, level.total_quantity);
            writer.u64(level.order_count);
          }
        } else {
          writer.u8(7U);
          writer.u32(static_cast<std::uint32_t>(value.error.code));
          writer.string(value.error.message);
        }
      },
      event.payload);
}

core::Result<ExchangeEvent> read_event(Reader& reader, const std::vector<core::Market>& markets) {
  const auto sequence = read_id<core::SequenceNumber>(reader);
  const auto time = read_timestamp(reader);
  const auto ingress = reader.u64();
  const auto type = reader.u8();
  if (!sequence || !time || !ingress || !type || ingress.value() == 0U)
    return Error(core::DomainErrorCode::CorruptJournal, "durable event header is invalid");
  ExchangeEvent event{
      sequence.value(), time.value(), ingress.value(),
      CommandRejected{Error(core::DomainErrorCode::CorruptJournal, "uninitialized durable event")}};
  if (type.value() == 1U) {
    const auto order = read_order(reader, markets);
    if (!order) return order.error();
    event.payload = OrderAcknowledged{order.value()};
  } else if (type.value() == 2U) {
    const auto trade = read_trade(reader, markets);
    if (!trade) return trade.error();
    event.payload =
        TradeExecuted{book::Execution{trade.value(), core::Fill::for_buyer(trade.value()),
                                      core::Fill::for_seller(trade.value())}};
  } else if (type.value() == 3U) {
    const auto update = read_update(reader);
    if (!update) return update.error();
    event.payload = OrderOutcome{update.value()};
  } else if (type.value() == 4U) {
    const auto update = read_update(reader);
    if (!update) return update.error();
    event.payload = CancellationAcknowledged{update.value()};
  } else if (type.value() == 5U) {
    const auto market = read_id<core::MarketId>(reader);
    const auto before = reader.u8();
    const auto after = reader.u8();
    if (!market || !before || !after || before.value() > 3U || after.value() > 3U)
      return Error(core::DomainErrorCode::CorruptJournal, "durable lifecycle event is invalid");
    event.payload =
        MarketStatusChanged{market.value(), static_cast<core::MarketStatus>(before.value()),
                            static_cast<core::MarketStatus>(after.value())};
  } else if (type.value() == 6U) {
    const auto contract = read_id<core::ContractId>(reader);
    const auto count = reader.u64();
    if (!contract || !count || count.value() > 1000000U)
      return Error(core::DomainErrorCode::CorruptJournal, "durable depth event is invalid");
    std::vector<PriceLevelDelta> levels;
    levels.reserve(static_cast<std::size_t>(count.value()));
    for (std::uint64_t i = 0; i < count.value(); ++i) {
      const auto side = reader.u8();
      const auto price = read_price(reader);
      const auto quantity = read_quantity(reader);
      const auto orders = reader.u64();
      if (!side || !price || !quantity || !orders || side.value() > 1U ||
          orders.value() > std::numeric_limits<std::size_t>::max())
        return Error(core::DomainErrorCode::CorruptJournal, "durable depth level is invalid");
      levels.push_back(PriceLevelDelta{static_cast<core::Side>(side.value()), price.value(),
                                       quantity.value(), static_cast<std::size_t>(orders.value())});
    }
    event.payload = BookDepthChanged{contract.value(), std::move(levels)};
  } else if (type.value() == 7U) {
    const auto code = reader.u32();
    const auto message = reader.string();
    if (!code || !message ||
        code.value() > static_cast<std::uint32_t>(core::DomainErrorCode::RecoveryRequired))
      return Error(core::DomainErrorCode::CorruptJournal, "durable rejection event is invalid");
    event.payload =
        CommandRejected{Error(static_cast<core::DomainErrorCode>(code.value()), message.value())};
  } else
    return Error(core::DomainErrorCode::CorruptJournal, "durable event type is unknown");
  return event;
}

void write_checkpoint(Writer& writer, const ExchangeCheckpoint& checkpoint, std::size_t committed) {
  writer.u64(committed);
  writer.u8(checkpoint.current_time.has_value() ? 1U : 0U);
  if (checkpoint.current_time) write_timestamp(writer, *checkpoint.current_time);
  writer.u64(checkpoint.next_order_id);
  writer.u64(checkpoint.next_trade_id);
  writer.u64(checkpoint.next_event_sequence);
  writer.u64(checkpoint.next_ingress_sequence);
  writer.u64(checkpoint.markets.size());
  for (const auto& market : checkpoint.markets) {
    write_market(writer, market.market);
    writer.u8(static_cast<std::uint8_t>(market.status));
    writer.u64(market.book.options.maximum_price_levels);
    writer.u64(market.book.resting_orders.size());
    for (const auto& order : market.book.resting_orders) {
      write_order(writer, order.order);
      write_quantity(writer, order.remaining_quantity);
      write_id(writer, order.priority_sequence);
    }
    write_id(writer, market.book.next_priority_sequence);
  }
}

core::Result<ExchangeSimulator::DurableStore::Snapshot> read_checkpoint(Reader& reader) {
  const auto committed = reader.u64();
  const auto has_time = reader.u8();
  if (!committed || !has_time || has_time.value() > 1U)
    return Error(core::DomainErrorCode::CorruptJournal, "durable checkpoint header is invalid");
  std::optional<core::Timestamp> time;
  if (has_time.value() == 1U) {
    const auto value = read_timestamp(reader);
    if (!value) return value.error();
    time = value.value();
  }
  const auto next_order = reader.u64();
  const auto next_trade = reader.u64();
  const auto next_event = reader.u64();
  const auto next_ingress = reader.u64();
  const auto market_count = reader.u64();
  if (!next_order || !next_trade || !next_event || !next_ingress || !market_count ||
      next_order.value() == 0U || next_trade.value() == 0U || next_event.value() == 0U ||
      next_ingress.value() == 0U || market_count.value() > 100000U)
    return Error(core::DomainErrorCode::CorruptJournal, "durable checkpoint counters are invalid");
  std::vector<MarketCheckpoint> markets;
  markets.reserve(static_cast<std::size_t>(market_count.value()));
  std::vector<core::Market> known;
  for (std::uint64_t i = 0; i < market_count.value(); ++i) {
    const auto market = read_market(reader);
    const auto status = reader.u8();
    const auto max_levels = reader.u64();
    const auto order_count = reader.u64();
    if (!market || !status || !max_levels || !order_count || status.value() > 3U ||
        max_levels.value() > std::numeric_limits<std::size_t>::max() ||
        order_count.value() > 10000000U)
      return Error(core::DomainErrorCode::CorruptJournal, "durable checkpoint market is invalid");
    known.push_back(market.value());
    std::vector<book::RestingOrderState> orders;
    orders.reserve(static_cast<std::size_t>(order_count.value()));
    for (std::uint64_t j = 0; j < order_count.value(); ++j) {
      const auto order = read_order(reader, known);
      const auto remaining = read_quantity(reader);
      const auto priority = read_id<core::SequenceNumber>(reader);
      if (!order || !remaining || !priority)
        return Error(core::DomainErrorCode::CorruptJournal,
                     "durable checkpoint resting order is invalid");
      orders.push_back(book::RestingOrderState{order.value(), remaining.value(), priority.value()});
    }
    const auto next_priority = read_id<core::SequenceNumber>(reader);
    if (!next_priority) return next_priority.error();
    markets.push_back(MarketCheckpoint{
        market.value(), static_cast<core::MarketStatus>(status.value()),
        book::BookCheckpoint{market.value().contract(),
                             book::BookOptions{static_cast<std::size_t>(max_levels.value())},
                             std::move(orders), next_priority.value()}});
  }
  return ExchangeSimulator::DurableStore::Snapshot{ExchangeCheckpoint{time,
                                                                      next_order.value(),
                                                                      next_trade.value(),
                                                                      next_event.value(),
                                                                      next_ingress.value(),
                                                                      std::move(markets),
                                                                      {}},
                                                   static_cast<std::size_t>(committed.value())};
}

std::vector<std::uint8_t> encode_scheduled(const ScheduledCommand& command) {
  Writer writer;
  write_scheduled(writer, command);
  return writer.take();
}
bool same_command(const ScheduledCommand& left, const ScheduledCommand& right) {
  return encode_scheduled(left) == encode_scheduled(right);
}
bool same_events(const std::vector<ExchangeEvent>& left, const std::vector<ExchangeEvent>& right) {
  Writer a;
  Writer b;
  a.u64(left.size());
  b.u64(right.size());
  for (const auto& value : left) write_event(a, value);
  for (const auto& value : right) write_event(b, value);
  return a.data() == b.data();
}

core::Result<void> write_file(const std::filesystem::path& path,
                              const std::vector<std::uint8_t>& bytes, bool append) {
  const int flags = O_WRONLY | O_CREAT | (append ? O_APPEND : O_TRUNC);
  const int fd = ::open(path.c_str(), flags, 0644);
  if (fd < 0) return Error(core::DomainErrorCode::IoFailure, "cannot open durable store file");
  std::size_t offset = 0;
  while (offset < bytes.size()) {
    const ssize_t written = ::write(fd, bytes.data() + offset, bytes.size() - offset);
    if (written <= 0) {
      ::close(fd);
      return Error(core::DomainErrorCode::IoFailure, "cannot write durable store file");
    }
    offset += static_cast<std::size_t>(written);
  }
  if (::fsync(fd) != 0) {
    ::close(fd);
    return Error(core::DomainErrorCode::IoFailure, "cannot fsync durable store file");
  }
  if (::close(fd) != 0)
    return Error(core::DomainErrorCode::IoFailure, "cannot close durable store file");
  return {};
}
core::Result<std::vector<std::uint8_t>> read_file(const std::filesystem::path& path) {
  const int fd = ::open(path.c_str(), O_RDONLY);
  if (fd < 0) return Error(core::DomainErrorCode::IoFailure, "cannot open durable store file");
  std::vector<std::uint8_t> bytes;
  std::array<std::uint8_t, 4096> buffer{};
  for (;;) {
    const ssize_t count = ::read(fd, buffer.data(), buffer.size());
    if (count < 0) {
      ::close(fd);
      return Error(core::DomainErrorCode::IoFailure, "cannot read durable store file");
    }
    if (count == 0) break;
    bytes.insert(bytes.end(), buffer.begin(), buffer.begin() + count);
  }
  ::close(fd);
  return bytes;
}
core::Result<void> fsync_directory(const std::filesystem::path& directory) {
  const int fd = ::open(directory.c_str(), O_RDONLY);
  if (fd < 0) {
    return Error(core::DomainErrorCode::IoFailure, "cannot open durable store directory");
  }
  if (::fsync(fd) != 0) {
    ::close(fd);
    return Error(core::DomainErrorCode::IoFailure, "cannot fsync durable store directory");
  }
  if (::close(fd) != 0) {
    return Error(core::DomainErrorCode::IoFailure, "cannot close durable store directory");
  }
  return {};
}
void append_u32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
  for (unsigned shift = 0; shift < 32; shift += 8)
    bytes.push_back(static_cast<std::uint8_t>(value >> shift));
}
void append_u16(std::vector<std::uint8_t>& bytes, std::uint16_t value) {
  for (unsigned shift = 0; shift < 16; shift += 8)
    bytes.push_back(static_cast<std::uint8_t>(value >> shift));
}
std::vector<std::uint8_t> header(const std::array<std::uint8_t, 8>& magic) {
  std::vector<std::uint8_t> result(magic.begin(), magic.end());
  append_u32(result, kVersion);
  return result;
}
std::vector<std::uint8_t> frame(FrameType type, const std::vector<std::uint8_t>& payload) {
  std::vector<std::uint8_t> result;
  append_u32(result, kFrameMagic);
  append_u16(result, static_cast<std::uint16_t>(type));
  append_u32(result, static_cast<std::uint32_t>(payload.size()));
  append_u32(result, crc32(payload));
  result.insert(result.end(), payload.begin(), payload.end());
  return result;
}
core::Result<void> validate_header(const std::vector<std::uint8_t>& bytes,
                                   const std::array<std::uint8_t, 8>& expected) {
  if (bytes.size() < 12U || !std::equal(expected.begin(), expected.end(), bytes.begin()))
    return Error(core::DomainErrorCode::CorruptJournal, "durable store header is invalid");
  Reader reader(bytes, 8, 12);
  const auto version = reader.u32();
  if (!version || version.value() != kVersion)
    return Error(core::DomainErrorCode::CorruptJournal, "durable store version is unsupported");
  return {};
}

}  // namespace

core::Result<std::unique_ptr<ExchangeSimulator::DurableStore>>
ExchangeSimulator::DurableStore::create(DurableStoreConfig config,
                                        const std::vector<core::Market>& markets) {
  if (config.directory.empty())
    return Error(core::DomainErrorCode::IoFailure, "durable store directory is empty");
  std::error_code error;
  std::filesystem::create_directories(config.directory, error);
  if (error)
    return Error(core::DomainErrorCode::IoFailure, "cannot create durable store directory");
  const auto journal = config.directory / "exchange.journal";
  if (std::filesystem::exists(journal))
    return Error(core::DomainErrorCode::IoFailure, "durable journal already exists");
  Writer genesis;
  genesis.u64(markets.size());
  for (const auto& market : markets) write_market(genesis, market);
  std::vector<std::uint8_t> bytes = header(kJournalHeader);
  const auto genesis_frame = frame(FrameType::Genesis, genesis.data());
  bytes.insert(bytes.end(), genesis_frame.begin(), genesis_frame.end());
  const auto saved = write_file(journal, bytes, false);
  if (!saved) return saved.error();
  const auto directory_synced = fsync_directory(config.directory);
  if (!directory_synced) return directory_synced.error();
  return std::make_unique<DurableStore>(std::move(config));
}

core::Result<std::pair<std::unique_ptr<ExchangeSimulator::DurableStore>,
                       ExchangeSimulator::DurableStore::Recovery>>
ExchangeSimulator::DurableStore::open(DurableStoreConfig config) {
  const auto bytes = read_file(config.directory / "exchange.journal");
  if (!bytes) return bytes.error();
  const auto valid = validate_header(bytes.value(), kJournalHeader);
  if (!valid) return valid.error();
  Recovery recovery;
  std::optional<ScheduledCommand> prepared;
  std::size_t offset = 12;
  bool genesis_seen = false;
  while (offset < bytes.value().size()) {
    if (bytes.value().size() - offset < kFrameHeaderSize) break;
    Reader frame_header(bytes.value(), offset, offset + kFrameHeaderSize);
    const auto magic = frame_header.u32();
    const auto type = frame_header.u16();
    const auto length = frame_header.u32();
    const auto checksum = frame_header.u32();
    if (!magic || !type || !length || !checksum)
      return Error(core::DomainErrorCode::CorruptJournal, "durable frame header is invalid");
    if (magic.value() != kFrameMagic ||
        length.value() > bytes.value().size() - offset - kFrameHeaderSize) {
      if (magic.value() == kFrameMagic) break;
      return Error(core::DomainErrorCode::CorruptJournal, "durable frame is corrupt");
    }
    const std::size_t payload_begin = offset + kFrameHeaderSize;
    const std::size_t payload_end = payload_begin + length.value();
    std::vector<std::uint8_t> payload(
        bytes.value().begin() + static_cast<std::ptrdiff_t>(payload_begin),
        bytes.value().begin() + static_cast<std::ptrdiff_t>(payload_end));
    if (crc32(payload) != checksum.value())
      return Error(core::DomainErrorCode::CorruptJournal, "durable frame checksum does not match");
    Reader reader(payload);
    if (type.value() == static_cast<std::uint16_t>(FrameType::Genesis)) {
      if (genesis_seen || prepared.has_value())
        return Error(core::DomainErrorCode::InconsistentJournal,
                     "durable genesis frame is out of order");
      const auto count = reader.u64();
      if (!count || count.value() > 100000U)
        return Error(core::DomainErrorCode::CorruptJournal, "durable genesis is invalid");
      for (std::uint64_t i = 0; i < count.value(); ++i) {
        const auto market = read_market(reader);
        if (!market) return market.error();
        recovery.markets.push_back(market.value());
      }
      genesis_seen = true;
    } else if (type.value() == static_cast<std::uint16_t>(FrameType::Prepared)) {
      if (!genesis_seen || prepared.has_value())
        return Error(core::DomainErrorCode::InconsistentJournal,
                     "durable prepared frame is out of order");
      const auto command = read_scheduled(reader);
      if (!command) return command.error();
      prepared = command.value();
    } else if (type.value() == static_cast<std::uint16_t>(FrameType::Committed)) {
      if (!prepared.has_value())
        return Error(core::DomainErrorCode::InconsistentJournal,
                     "durable commit has no prepared command");
      const auto command = read_scheduled(reader);
      const auto event_count = reader.u64();
      if (!command || !event_count || !same_command(command.value(), *prepared) ||
          event_count.value() > 1000000U)
        return Error(core::DomainErrorCode::InconsistentJournal,
                     "durable commit does not match prepared command");
      std::vector<ExchangeEvent> events;
      events.reserve(static_cast<std::size_t>(event_count.value()));
      for (std::uint64_t i = 0; i < event_count.value(); ++i) {
        const auto event = read_event(reader, recovery.markets);
        if (!event) return event.error();
        events.push_back(event.value());
      }
      recovery.commits.push_back(Commit{command.value(), std::move(events)});
      prepared.reset();
    } else
      return Error(core::DomainErrorCode::CorruptJournal, "durable frame type is unknown");
    if (!reader.done())
      return Error(core::DomainErrorCode::CorruptJournal, "durable frame has trailing data");
    offset = payload_end;
  }
  if (!genesis_seen)
    return Error(core::DomainErrorCode::CorruptJournal, "durable journal has no genesis frame");
  recovery.prepared_command = prepared;
  auto store = std::make_unique<DurableStore>(std::move(config));
  store->prepared_command_ = prepared;
  store->recovery_commits_ = recovery.commits;
  const auto snapshot_path = store->config_.directory / "exchange.snapshot";
  if (std::filesystem::exists(snapshot_path)) {
    const auto snapshot_bytes = read_file(snapshot_path);
    if (!snapshot_bytes) return snapshot_bytes.error();
    const auto snapshot_valid = validate_header(snapshot_bytes.value(), kSnapshotHeader);
    if (!snapshot_valid) return snapshot_valid.error();
    if (snapshot_bytes.value().size() < 16U) {
      return Error(core::DomainErrorCode::CorruptJournal, "durable checkpoint is truncated");
    }
    Reader checksum_reader(snapshot_bytes.value(), 12, 16);
    const auto expected_checksum = checksum_reader.u32();
    std::vector<std::uint8_t> snapshot_payload(snapshot_bytes.value().begin() + 16,
                                               snapshot_bytes.value().end());
    if (!expected_checksum || crc32(snapshot_payload) != expected_checksum.value()) {
      return Error(core::DomainErrorCode::CorruptJournal,
                   "durable checkpoint checksum does not match");
    }
    Reader snapshot_reader(snapshot_bytes.value(), 16);
    const auto snapshot = read_checkpoint(snapshot_reader);
    if (!snapshot || !snapshot_reader.done())
      return Error(core::DomainErrorCode::CorruptJournal, "durable checkpoint is invalid");
    recovery.snapshot = snapshot.value();
  }
  return std::pair<std::unique_ptr<DurableStore>, Recovery>{std::move(store), std::move(recovery)};
}

core::Result<void> ExchangeSimulator::DurableStore::prepare(const ScheduledCommand& command) {
  if (recovery_index_ < recovery_commits_.size()) {
    if (!same_command(command, recovery_commits_[recovery_index_].command))
      return Error(core::DomainErrorCode::InconsistentJournal,
                   "recovery command does not match durable journal");
    return {};
  }
  if (prepared_command_.has_value()) {
    if (same_command(command, *prepared_command_)) return {};
    return Error(core::DomainErrorCode::InconsistentJournal,
                 "durable journal already has a prepared command");
  }
  Writer writer;
  write_scheduled(writer, command);
  const auto saved = write_file(config_.directory / "exchange.journal",
                                frame(FrameType::Prepared, writer.data()), true);
  if (!saved) return saved.error();
  prepared_command_ = command;
  return {};
}

core::Result<void> ExchangeSimulator::DurableStore::commit(
    const ScheduledCommand& command, const std::vector<ExchangeEvent>& events) {
  if (recovery_index_ < recovery_commits_.size()) {
    const Commit& expected = recovery_commits_[recovery_index_];
    if (!same_command(command, expected.command) || !same_events(events, expected.events))
      return Error(core::DomainErrorCode::InconsistentJournal,
                   "recovery event batch does not match durable journal");
    ++recovery_index_;
    return {};
  }
  if (!prepared_command_.has_value() || !same_command(command, *prepared_command_))
    return Error(core::DomainErrorCode::InconsistentJournal,
                 "durable commit does not match prepared command");
  Writer writer;
  write_scheduled(writer, command);
  writer.u64(events.size());
  for (const auto& event : events) write_event(writer, event);
  const auto saved = write_file(config_.directory / "exchange.journal",
                                frame(FrameType::Committed, writer.data()), true);
  if (!saved) return saved.error();
  prepared_command_.reset();
  return {};
}

core::Result<void> ExchangeSimulator::DurableStore::save_checkpoint(
    const ExchangeCheckpoint& checkpoint, std::size_t committed_command_count) {
  Writer writer;
  write_checkpoint(writer, checkpoint, committed_command_count);
  std::vector<std::uint8_t> bytes = header(kSnapshotHeader);
  append_u32(bytes, crc32(writer.data()));
  bytes.insert(bytes.end(), writer.data().begin(), writer.data().end());
  const auto temporary = config_.directory / "exchange.snapshot.tmp";
  const auto saved = write_file(temporary, bytes, false);
  if (!saved) return saved.error();
  std::error_code error;
  std::filesystem::rename(temporary, config_.directory / "exchange.snapshot", error);
  if (error)
    return Error(core::DomainErrorCode::IoFailure, "cannot atomically replace durable checkpoint");
  return fsync_directory(config_.directory);
}

core::Result<void> ExchangeSimulator::DurableStore::begin_recovery_replay(
    std::size_t committed_command_count) {
  if (committed_command_count > recovery_commits_.size())
    return Error(core::DomainErrorCode::InconsistentJournal,
                 "durable checkpoint is ahead of recovery journal");
  recovery_index_ = committed_command_count;
  return {};
}
core::Result<void> ExchangeSimulator::DurableStore::finish_recovery_replay() const {
  if (recovery_index_ != recovery_commits_.size())
    return Error(core::DomainErrorCode::InconsistentJournal,
                 "durable recovery did not replay every committed command");
  if (prepared_command_.has_value())
    return Error(core::DomainErrorCode::RecoveryRequired,
                 "durable recovery left a prepared command uncommitted");
  return {};
}

}  // namespace pmm::sim
