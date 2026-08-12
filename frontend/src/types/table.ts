/** Mirrors backend/data_models/order.py's TableStatus enum values exactly. */
export type TableStatus = "available" | "occupied" | "reserved";

/** Mirrors the JSON shape of backend/data_models/order.py's TableResponse. */
export interface Table {
  id: number;
  table_number: number;
  capacity: number;
  status: TableStatus;
}
