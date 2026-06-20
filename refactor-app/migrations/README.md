# Migrations

`docs/schema/001_initial_schema.sql` 是设计真源。

`migrations/sql/001_initial_schema.sql` 是 P0 阶段可执行 SQL 迁移副本。

后续接 Alembic revision 时，必须保持 Alembic 迁移与 SQL 真源一致。
