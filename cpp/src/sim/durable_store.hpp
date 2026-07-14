#pragma once

#include <cstddef>
#include <memory>
#include <optional>
#include <vector>

#include "pmm/sim/exchange_simulator.hpp"

namespace pmm::sim {

class ExchangeSimulator::DurableStore {
 public:
  struct Commit {
    ScheduledCommand command;
    std::vector<ExchangeEvent> events;
  };

  struct Snapshot {
    ExchangeCheckpoint checkpoint;
    std::size_t committed_command_count;
  };

  struct Recovery {
    std::vector<core::Market> markets;
    std::optional<Snapshot> snapshot;
    std::vector<Commit> commits;
    std::optional<ScheduledCommand> prepared_command;
  };

  [[nodiscard]] static core::Result<std::unique_ptr<DurableStore>> create(
      DurableStoreConfig config, const std::vector<core::Market>& markets);
  [[nodiscard]] static core::Result<std::pair<std::unique_ptr<DurableStore>, Recovery>> open(
      DurableStoreConfig config);

  [[nodiscard]] core::Result<void> prepare(const ScheduledCommand& command);
  [[nodiscard]] core::Result<void> commit(const ScheduledCommand& command,
                                          const std::vector<ExchangeEvent>& events);
  [[nodiscard]] core::Result<void> save_checkpoint(const ExchangeCheckpoint& checkpoint,
                                                   std::size_t committed_command_count);
  [[nodiscard]] core::Result<void> begin_recovery_replay(std::size_t committed_command_count);
  [[nodiscard]] core::Result<void> finish_recovery_replay() const;

  explicit DurableStore(DurableStoreConfig config) : config_(std::move(config)) {}

 private:
  DurableStoreConfig config_;
  std::vector<Commit> recovery_commits_;
  std::size_t recovery_index_ = 0;
  std::optional<ScheduledCommand> prepared_command_;
};

}  // namespace pmm::sim
