# Public C++ headers

This directory contains stable, project-owned C++ interfaces. The Phase 2 core domain model is
available through `pmm/core/core.hpp`; the Phase 3 limit order book is available through
`pmm/book/order_book.hpp`. The latter owns mutable matching state only. Simulation, strategy,
risk, market lifecycle, persistence, and exchange-gateway interfaces remain later phases.
