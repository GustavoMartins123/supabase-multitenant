defmodule AnalyticsTranslationSmoke do
  alias Logflare.Sql.DialectTranslation

  def run! do
    timeseries =
      translate!("""
      WITH postgres_logs AS (
        SELECT t.timestamp, t.id, t.event_message, t.metadata
        FROM `postgres.logs` AS t
      ),
      unified_logs AS (
        SELECT
          id,
          pgl.timestamp AS timestamp,
          'postgres' AS log_type,
          CASE
            WHEN parsed.error_severity = 'LOG' THEN 'success'
            WHEN parsed.error_severity = 'WARNING' THEN 'warning'
            ELSE 'error'
          END AS level
        FROM postgres_logs AS pgl
        CROSS JOIN UNNEST(pgl.metadata) AS metadata
        CROSS JOIN UNNEST(metadata.parsed) AS parsed
      )
      SELECT
        TIMESTAMP_TRUNC(timestamp, MINUTE) AS time_bucket,
        COUNTIF(level = 'success') AS success,
        COUNTIF(level = 'warning') AS warning,
        COUNTIF(level = 'error') AS error,
        COUNT(*) AS total_per_bucket
      FROM unified_logs
      WHERE log_type IN ('postgres', 'postgrest')
      GROUP BY time_bucket
      ORDER BY time_bucket ASC
      """)

    assert_contains!(timeseries, "date_trunc('minute'")
    assert_contains!(timeseries, "to_jsonb(level)")
    assert_contains!(timeseries, "group by time_bucket")
    refute_contains!(timeseries, "body -> 'time_bucket'")
    refute_contains!(timeseries, "body ->> 'time_bucket'")

    facets =
      translate!("""
      WITH unified_logs AS (
        SELECT
          'postgres' AS log_type,
          CASE WHEN id IS NOT NULL THEN 'success' ELSE 'error' END AS level,
          'GET' AS method
        FROM `postgres.logs`
      ),
      log_type_counts AS (
        SELECT
          COUNT(*) AS total,
          COUNTIF(log_type = 'postgres') AS postgres_count
        FROM unified_logs
        WHERE log_type IS NOT NULL
      ),
      level_counts AS (
        SELECT
          COUNTIF(level = 'success') AS success_count,
          COUNTIF(level = 'warning') AS warning_count,
          COUNTIF(level = 'error') AS error_count
        FROM unified_logs
      ),
      method_count AS (
        SELECT 'method' AS dimension, method AS value, COUNT(*) AS count
        FROM unified_logs
        WHERE method IS NOT NULL
        GROUP BY method
      )
      SELECT 'total' AS dimension, 'all' AS value, total AS count FROM log_type_counts
      UNION ALL SELECT 'log_type', 'postgres', postgres_count FROM log_type_counts
      UNION ALL SELECT 'level', 'success', success_count FROM level_counts
      UNION ALL SELECT 'level', 'warning', warning_count FROM level_counts
      UNION ALL SELECT 'level', 'error', error_count FROM level_counts
      UNION ALL SELECT dimension, value, count FROM method_count
      """)

    assert_contains!(facets, "to_jsonb(log_type)")
    assert_contains!(facets, "to_jsonb(level)")
    refute_contains!(facets, "cast(log_type as jsonb)")
    refute_contains!(facets, "cast(level as jsonb)")
  end

  defp translate!(query) do
    {:ok, translated} = DialectTranslation.translate_bq_to_pg(query, "_analytics")
    String.downcase(translated)
  end

  defp assert_contains!(query, expected) do
    unless String.contains?(query, expected) do
      raise "expected translated query to contain #{inspect(expected)}:\n#{query}"
    end
  end

  defp refute_contains!(query, unexpected) do
    if String.contains?(query, unexpected) do
      raise "expected translated query not to contain #{inspect(unexpected)}:\n#{query}"
    end
  end
end

AnalyticsTranslationSmoke.run!()
