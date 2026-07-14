defmodule Logflare.Sql.DialectTranslation do
  @moduledoc """
  Handles translation between SQL dialects, specifically BigQuery to PostgreSQL.
  """

  require Logger

  import Logflare.Utils.Guards

  alias Logflare.Sql.Parser
  alias Logflare.Sql.AstUtils

  @doc """
  Translates BigQuery SQL to PostgreSQL SQL.
  """
  @spec translate_bq_to_pg(query :: String.t(), schema_prefix :: String.t() | nil) ::
          {:ok, String.t()} | {:error, String.t()}
  def translate_bq_to_pg(query, schema_prefix \\ nil) when is_non_empty_binary(query) do
    {:ok, stmts} = Parser.parse("bigquery", query)

    for ast <- stmts do
      ast
      |> bq_to_pg_convert_tables()
      |> bq_to_pg_convert_functions()
      |> bq_to_pg_field_references()
      |> pg_traverse_final_pass()
    end
    |> then(fn ast ->
      params = extract_all_parameters(ast)

      {:ok, query_string} =
        ast
        |> Parser.to_string()

      # explicitly set the schema prefix of the table
      replacement_pattern =
        if schema_prefix do
          ~s|"#{schema_prefix}"."log_events_\\g{2}"|
        else
          "\"log_events_\\g{2}\""
        end

      converted =
        query_string
        |> bq_to_pg_convert_parameters(params)
        # TODO: remove once sqlparser-rs bug is fixed
        # parser for postgres adds parenthesis to the end for postgres
        |> String.replace(~r/current\_timestamp\(\)/im, "current_timestamp")
        |> String.replace(~r/\"([\w\_\-]*\.[\w\_\-]+)\.([\w_]{36})"/im, replacement_pattern)

      Logger.debug(
        "Postgres translation is complete: #{query} | \n output: #{inspect(converted, limit: :infinity)}"
      )

      {:ok, converted}
    end)
  end

  @spec extract_all_parameters(ast :: any()) :: [String.t()]
  defp extract_all_parameters(ast) do
    AstUtils.collect_from_ast(ast, &do_extract_parameters/1) |> Enum.uniq()
  end

  @spec do_extract_parameters(ast_node :: any()) :: {:collect, String.t()} | :skip
  defp do_extract_parameters({"Placeholder", "@" <> value}), do: {:collect, value}
  defp do_extract_parameters(_ast_node), do: :skip

  @spec bq_to_pg_convert_parameters(string :: String.t(), params :: [String.t()]) :: String.t()
  defp bq_to_pg_convert_parameters(string, []), do: string

  defp bq_to_pg_convert_parameters(string, params) do
    do_parameter_positions_mapping(string, params)
    |> Map.to_list()
    |> Enum.sort_by(fn {i, _v} -> i end, :asc)
    |> Enum.reduce(string, fn {index, param}, acc ->
      Regex.replace(~r/@#{param}(?!:\s|$)/, acc, "$#{index}::text", global: false)
    end)
  end

  @spec do_parameter_positions_mapping(query :: String.t(), params :: [String.t()]) :: %{
          pos_integer() => String.t()
        }
  defp do_parameter_positions_mapping(_query, []), do: %{}

  defp do_parameter_positions_mapping(query, params)
       when is_non_empty_binary(query) and is_list(params) do
    str =
      params
      |> Enum.uniq()
      |> Enum.join("|")

    regexp = Regex.compile!("@(#{str})(?:\\s|$|\\,|\\,|\\)|\\()")

    Regex.scan(regexp, query)
    |> Enum.with_index(1)
    |> Enum.reduce(%{}, fn {[_, param], index}, acc ->
      Map.put(acc, index, String.trim(param))
    end)
  end

  @spec bq_to_pg_convert_tables(ast :: any()) :: any()
  defp bq_to_pg_convert_tables(ast) do
    AstUtils.transform_recursive(ast, nil, &do_bq_to_pg_convert_tables/2)
  end

  defp do_bq_to_pg_convert_tables({"Table" = k, v}, _data) do
    {quote_style, table_name} =
      case Map.get(v, "name") do
        [%{"quote_style" => quote_style, "value" => value}] ->
          {quote_style, value}

        [%{"quote_style" => quote_style, "value" => _} | _] = values ->
          value = Enum.map_join(values, ".", & &1["value"])
          {quote_style, value}
      end

    {k,
     %{
       v
       | "name" => [AstUtils.build_identifier(table_name, quote_style)]
     }}
  end

  defp do_bq_to_pg_convert_tables(ast_node, _data), do: {:recurse, ast_node}

  @spec bq_to_pg_convert_functions(ast :: any()) :: any()
  defp bq_to_pg_convert_functions(ast) do
    AstUtils.transform_recursive(ast, nil, &do_bq_to_pg_convert_functions/2)
  end

  defp do_bq_to_pg_convert_functions({k, v} = kv, _data)
       when k in ["Function", "AggregateExpressionWithFilter"] do
    function_name = v |> get_in(["name", Access.at(0), "value"]) |> String.downcase()

    case function_name do
      "regexp_contains" ->
        string =
          get_function_arg(v, 0)
          |> case do
            %{"CompoundIdentifier" => _arr} = identifier ->
              identifier

            %{"Identifier" => _arr} = identifier ->
              identifier

            %{"Value" => %{"DoubleQuotedString" => value}} when is_non_empty_binary(value) ->
              %{"Value" => %{"SingleQuotedString" => value}}

            _ ->
              %{"Value" => %{"SingleQuotedString" => ""}}
          end

        pattern =
          get_function_arg(v, 1)
          |> case do
            %{"Value" => %{"DoubleQuotedString" => value}} when is_non_empty_binary(value) ->
              %{"Value" => %{"SingleQuotedString" => value}}

            %{"Value" => %{"SingleQuotedString" => value}} when is_non_empty_binary(value) ->
              %{"Value" => %{"SingleQuotedString" => value}}

            _ ->
              %{"Value" => %{"SingleQuotedString" => ""}}
          end

        {"BinaryOp", %{"left" => string, "op" => "PGRegexMatch", "right" => pattern}}

      "countif" ->
        filter = get_function_arg(v, 0)

        {k,
         %{
           v
           | "args" => %{
               "List" => %{
                 "args" => [%{"Unnamed" => "Wildcard"}],
                 "clauses" => [],
                 "duplicate_treatment" => nil
               }
             },
             "filter" => bq_to_pg_convert_functions(filter),
             "name" => [AstUtils.build_identifier("count")]
         }}

      "timestamp_sub" ->
        to_sub = get_function_arg(v, 0)
        interval = get_in(get_function_arg(v, 1), ["Interval"])
        interval_type = interval["leading_field"]
        interval_value_str = get_in(interval, ["value", "Value", "Number", Access.at(0)])
        pg_interval = String.downcase("#{interval_value_str} #{interval_type}")

        {"BinaryOp",
         %{
           "left" => bq_to_pg_convert_functions(to_sub),
           "op" => "Minus",
           "right" => %{
             "Interval" => %{
               "fractional_seconds_precision" => nil,
               "last_field" => nil,
               "leading_field" => nil,
               "leading_precision" => nil,
               "value" => %{"Value" => %{"SingleQuotedString" => pg_interval}}
             }
           }
         }}

      "timestamp_trunc" ->
        to_trunc = get_function_arg(v, 0)

        interval_type =
          get_in(get_function_arg(v, 1), ["Identifier", "value"])
          |> String.downcase()

        field_arg =
          if timestamp_identifier?(to_trunc) do
            at_time_zone(to_trunc, :double_colon)
          else
            bq_to_pg_convert_functions(to_trunc)
          end

        {k,
         %{
           v
           | "args" => %{
               "List" => %{
                 "args" => [
                   %{
                     "Unnamed" => %{
                       "Expr" => %{"Value" => %{"SingleQuotedString" => interval_type}}
                     }
                   },
                   %{
                     "Unnamed" => %{"Expr" => field_arg}
                   }
                 ],
                 "clauses" => [],
                 "duplicate_treatment" => nil
               }
             },
             "name" => [AstUtils.build_identifier("date_trunc")]
         }}

      _ ->
        kv
    end
  end

  defp do_bq_to_pg_convert_functions(ast_node, _data), do: {:recurse, ast_node}

  # Handle CAST to numeric types - add ::TEXT first for identifiers (fixes JSONB cast errors)
  defp pg_traverse_final_pass(
         {"Cast" = k,
          %{
            "expr" => %{"Identifier" => _} = identifier,
            "data_type" => data_type
          } = v}
       )
       when is_map_key(data_type, "BigInt") or is_map_key(data_type, "Int") or
              is_map_key(data_type, "SmallInt") or is_map_key(data_type, "Numeric") or
              is_map_key(data_type, "Decimal") or is_map_key(data_type, "Float") or
              is_map_key(data_type, "Double") do
    text_cast = %{
      "Cast" => %{
        "data_type" => %{"Text" => nil},
        "expr" => identifier,
        "format" => nil,
        "kind" => "DoubleColon"
      }
    }

    {k,
     %{
       "kind" => Map.get(v, "kind", "Cast"),
       "expr" => text_cast,
       "data_type" => data_type,
       "format" => Map.get(v, "format")
     }}
  end

  # Handle CAST to numeric types for CompoundIdentifiers
  defp pg_traverse_final_pass(
         {"Cast" = k,
          %{
            "expr" => %{"CompoundIdentifier" => _} = compound,
            "data_type" => data_type
          } = v}
       )
       when is_map_key(data_type, "BigInt") or is_map_key(data_type, "Int") or
              is_map_key(data_type, "SmallInt") or is_map_key(data_type, "Numeric") or
              is_map_key(data_type, "Decimal") or is_map_key(data_type, "Float") or
              is_map_key(data_type, "Double") do
    text_cast = %{
      "Cast" => %{
        "data_type" => %{"Text" => nil},
        "expr" => compound,
        "format" => nil,
        "kind" => "DoubleColon"
      }
    }

    {k,
     %{
       "kind" => Map.get(v, "kind", "Cast"),
       "expr" => text_cast,
       "data_type" => data_type,
       "format" => Map.get(v, "format")
     }}
  end

  # Handle other CAST expressions
  defp pg_traverse_final_pass({"Cast" = k, %{"expr" => expr, "data_type" => data_type} = v}) do
    processed_expr =
      case expr do
        %{"Nested" => %{"BinaryOp" => %{"op" => op} = bin_op}}
        when op in ["Arrow", "HashArrow"] ->
          text_operator = if op == "Arrow", do: "LongArrow", else: "HashLongArrow"
          %{"Nested" => %{"BinaryOp" => %{bin_op | "op" => text_operator}}}

        other ->
          pg_traverse_final_pass(other)
      end

    # Convert INT64 to BigInt for PostgreSQL
    converted_data_type =
      case data_type do
        "Int64" ->
          %{"BigInt" => nil}

        %{"Custom" => %{"ObjectName" => [%{"value" => "INT64"}]}} ->
          %{"BigInt" => nil}

        %{"String" => _} ->
          %{"Text" => nil}

        "String" ->
          %{"Text" => nil}

        %{"Custom" => %{"ObjectName" => [%{"value" => "STRING"}]}} ->
          %{"Text" => nil}

        other ->
          other
      end

    # Convert SafeCast to regular Cast (BigQuery SAFE_CAST to PostgreSQL CAST)
    converted_kind =
      case Map.get(v, "kind") do
        "SafeCast" -> "Cast"
        other -> other || "Cast"
      end

    {k,
     %{
       "kind" => converted_kind,
       "expr" => processed_expr,
       "data_type" => converted_data_type,
       "format" => Map.get(v, "format")
     }}
  end

  defp pg_traverse_final_pass({"Function" = k, %{"name" => [%{"value" => function_name}]} = v})
       when function_name in ["DATE_TRUNC", "date_trunc"] do
    processed_args =
      case v do
        %{"args" => %{"List" => %{"args" => args} = list_args} = args_wrapper} ->
          converted_args =
            Enum.map(args, fn
              %{
                "Unnamed" => %{
                  "Expr" => %{"Nested" => %{"BinaryOp" => %{"op" => "Arrow"} = bin_op}}
                }
              } ->
                %{
                  "Unnamed" => %{
                    "Expr" => %{"Nested" => %{"BinaryOp" => %{bin_op | "op" => "LongArrow"}}}
                  }
                }

              other_arg ->
                other_arg
            end)

          %{v | "args" => %{args_wrapper | "List" => %{list_args | "args" => converted_args}}}

        other ->
          other
      end

    {k, processed_args}
  end

  # between operator should have values cast to numeric
  defp pg_traverse_final_pass({"Between" = k, %{"expr" => expr} = v}) do
    processed_expr =
      case expr do
        %{"Nested" => %{"BinaryOp" => %{"op" => "Arrow"} = bin_op}} ->
          %{"Nested" => %{"BinaryOp" => %{bin_op | "op" => "LongArrow"}}}

        other ->
          other
      end

    new_expr = processed_expr |> pg_traverse_final_pass() |> cast_to_numeric()
    {k, %{v | "expr" => new_expr}}
  end

  # handle binary operations comparison casting
  defp pg_traverse_final_pass(
         {"BinaryOp" = k,
          %{
            "left" => left,
            "right" => right,
            "op" => operator
          } = v}
       ) do
    # handle left/right numeric value comparisons
    is_numeric_comparison = numeric_value?(left) or numeric_value?(right)
    # check if this is a regex operator - these require text on both sides
    is_regex_operator =
      operator in ["PGRegexMatch", "PGRegexIMatch", "PGRegexNotMatch", "PGRegexNotIMatch"]

    # Process left side
    processed_left =
      cond do
        match?(%{"Value" => _}, left) ->
          left

        is_numeric_comparison and (identifier?(left) or json_access?(left)) ->
          left
          |> cast_to_jsonb_double_colon()
          |> jsonb_to_text()
          |> cast_to_numeric()

        is_regex_operator and identifier?(left) ->
          # Cast identifiers to text for regex operations
          # This handles CTE fields that might be JSONB
          %{
            "Cast" => %{
              "data_type" => %{"Text" => nil},
              "expr" => left,
              "format" => nil,
              "kind" => "DoubleColon"
            }
          }

        is_regex_operator and json_access?(left) ->
          # For regex operators, ensure JSONB accessors return text
          # Convert Arrow (->) to LongArrow (->>)
          case left do
            %{"Nested" => %{"BinaryOp" => %{"op" => "Arrow"} = bin_op}} ->
              %{"Nested" => %{"BinaryOp" => %{bin_op | "op" => "LongArrow"}}}

            other ->
              pg_traverse_final_pass(other)
          end

        timestamp_identifier?(left) ->
          at_time_zone(left, :cast)

        identifier?(left) and operator == "Eq" ->
          left
          |> to_jsonb()
          |> jsonb_to_text()

        true ->
          pg_traverse_final_pass(left)
      end

    # Process right side
    processed_right =
      cond do
        match?(%{"Value" => _}, right) ->
          right

        is_numeric_comparison and (identifier?(right) or json_access?(right)) ->
          right
          |> cast_to_jsonb_double_colon()
          |> jsonb_to_text()
          |> cast_to_numeric()

        timestamp_identifier?(right) ->
          at_time_zone(right, :cast)

        identifier?(right) and operator == "Eq" ->
          right
          |> to_jsonb()
          |> jsonb_to_text()

        true ->
          pg_traverse_final_pass(right)
      end

    {k, %{v | "left" => processed_left, "right" => processed_right} |> pg_traverse_final_pass()}
  end

  # handle InList expressions - convert Arrow to LongArrow for text comparison
  defp pg_traverse_final_pass({"InList" = k, %{"expr" => expr} = v}) do
    processed_expr =
      case expr do
        %{"Nested" => %{"BinaryOp" => %{"op" => "Arrow"} = bin_op}} ->
          %{"Nested" => %{"BinaryOp" => %{bin_op | "op" => "LongArrow"}}}

        other ->
          pg_traverse_final_pass(other)
      end

    {k, %{v | "expr" => processed_expr}}
  end

  # convert backticks to double quotes
  defp pg_traverse_final_pass({"quote_style" = k, "`"}), do: {k, "\""}

  # ensure SingleQuotedString always has a string value, never null
  defp pg_traverse_final_pass({"SingleQuotedString" = k, v}) when not is_binary(v) do
    {k, ""}
  end

  # ensure DoubleQuotedString always has a string value, never null
  defp pg_traverse_final_pass({"DoubleQuotedString" = k, v}) when not is_binary(v) do
    {k, ""}
  end

  # Clean up CompoundIdentifier by filtering out null/empty values
  # This prevents Rust NIF panics while preserving semantic meaning
  defp pg_traverse_final_pass({"CompoundIdentifier" = k, identifiers})
       when is_list(identifiers) do
    # Filter out null or empty identifier parts
    valid_identifiers =
      Enum.filter(identifiers, fn
        %{"value" => nil} -> false
        %{"value" => ""} -> false
        _ -> true
      end)

    case valid_identifiers do
      # If we have valid identifiers, keep as CompoundIdentifier
      [_ | _] = valid ->
        {k, valid}

      # If no valid identifiers remain, this is an error case - use empty Identifier
      [] ->
        {"Identifier", AstUtils.build_identifier("")}
    end
  end

  # Ensure all identifier values are strings, never null
  defp pg_traverse_final_pass({"value" = k, nil}) do
    {k, ""}
  end

  # drop cross join unnest
  defp pg_traverse_final_pass({"joins" = k, joins}) do
    filtered_joins =
      for j <- joins,
          Map.get(j, "join_operator") != "CrossJoin",
          !is_map_key(Map.get(j, "relation"), "UNNEST") do
        j
      end

    {k, filtered_joins}
  end

  defp pg_traverse_final_pass({k, v}) when is_list(v) or is_map(v) do
    {k, pg_traverse_final_pass(v)}
  end

  defp pg_traverse_final_pass(kv) when is_list(kv) do
    Enum.map(kv, fn kv -> pg_traverse_final_pass(kv) end)
  end

  defp pg_traverse_final_pass(kv) when is_map(kv) do
    Enum.map(kv, fn kv -> pg_traverse_final_pass(kv) end) |> Map.new()
  end

  defp pg_traverse_final_pass(kv), do: kv

  @spec bq_to_pg_field_references(ast :: any()) :: any()
  defp bq_to_pg_field_references(ast) do
    joins = get_in(ast, ["Query", "body", "Select", "from", Access.at(0), "joins"]) || []
    cleaned_joins = Enum.filter(joins, fn join -> get_in(join, ["relation", "UNNEST"]) == nil end)

    ast
    |> traverse_convert_identifiers(%{
      alias_path_mappings: %{},
      cte_aliases: %{},
      in_cte_tables_tree: false,
      in_function_or_cast: false,
      in_projection_tree: false,
      from_sources: %{},
      in_binaryop: false,
      in_between: false,
      in_inlist: false,
      select_aliases: [],
      unnest_mappings: %{}
    })
    |> then(fn
      ast when joins != [] ->
        put_in(ast, ["Query", "body", "Select", "from", Access.at(0), "joins"], cleaned_joins)

      ast ->
        ast
    end)
  end

  defp cte_projection_aliases(nil), do: []

  defp cte_projection_aliases(tree) do
    tree
    |> get_in(["query", "body"])
    |> query_projection_aliases()
  end

  defp query_projection_aliases(%{"Select" => %{"projection" => projection}}) do
    for field <- projection,
        {expr, identifier} <- field,
        expr in ["UnnamedExpr", "ExprWithAlias"],
        alias_name = get_identifier_alias(identifier),
        is_binary(alias_name) do
      alias_name
    end
  end

  defp query_projection_aliases(%{"SetOperation" => %{"left" => left}}) do
    query_projection_aliases(left)
  end

  defp query_projection_aliases(_body), do: []

  defp convert_keys_to_json_query(identifiers, data, base \\ "body")

  # convert body.timestamp from unix microsecond to postgres timestamp
  defp convert_keys_to_json_query(
         %{"CompoundIdentifier" => [%{"value" => "timestamp"}]},
         %{
           in_cte_tables_tree: in_cte_tables_tree,
           cte_aliases: cte_aliases,
           in_projection_tree: false
         } = _data,
         [
           table,
           "body"
         ]
       )
       when cte_aliases == %{} or in_cte_tables_tree == true do
    at_time_zone(
      %{
        "Nested" => %{
          "BinaryOp" => %{
            "left" => %{
              "CompoundIdentifier" => [
                AstUtils.build_identifier(table),
                AstUtils.build_identifier("body")
              ]
            },
            "op" => "LongArrow",
            "right" => %{
              "Value" => %{"SingleQuotedString" => "timestamp"}
            }
          }
        }
      },
      :double_colon
    )
  end

  defp convert_keys_to_json_query(%{"Identifier" => %{"value" => "timestamp"}}, _data, "body") do
    at_time_zone(
      %{
        "Nested" => %{
          "BinaryOp" => %{
            "left" => %{
              "Identifier" => AstUtils.build_identifier("body")
            },
            "op" => "LongArrow",
            "right" => %{
              "Value" => %{"SingleQuotedString" => "timestamp"}
            }
          }
        }
      },
      :double_colon
    )
  end

  defp convert_keys_to_json_query(
         %{"CompoundIdentifier" => [%{"value" => key}]},
         data,
         [table, field]
       ) do
    %{
      "Nested" => %{
        "BinaryOp" => %{
          "left" => %{
            "CompoundIdentifier" => [
              AstUtils.build_identifier(table),
              AstUtils.build_identifier(field)
            ]
          },
          "op" => select_json_operator(data, false),
          "right" => %{
            "Value" => %{"SingleQuotedString" => key}
          }
        }
      }
    }
  end

  defp convert_keys_to_json_query(
         %{"CompoundIdentifier" => [%{"value" => key}]},
         data,
         base
       ) do
    %{
      "Nested" => %{
        "BinaryOp" => %{
          "left" => %{"Identifier" => AstUtils.build_identifier(base)},
          "op" => select_json_operator(data, false),
          "right" => %{
            "Value" => %{"SingleQuotedString" => key}
          }
        }
      }
    }
  end

  defp convert_keys_to_json_query(
         %{"CompoundIdentifier" => [%{"value" => join_alias}, %{"value" => key} | _]},
         data,
         base
       ) do
    case data.alias_path_mappings[join_alias] do
      nil ->
        # alias not found in mappings - return simple JSON access
        %{
          "Nested" => %{
            "BinaryOp" => %{
              "left" => %{"Identifier" => AstUtils.build_identifier(base)},
              "op" => select_json_operator(data, false),
              "right" => %{
                "Value" => %{"SingleQuotedString" => key}
              }
            }
          }
        }

      alias_path ->
        str_path = Enum.join(alias_path, ",")
        path = "{#{str_path},#{key}}"

        %{
          "Nested" => %{
            "BinaryOp" => %{
              "left" => %{"Identifier" => AstUtils.build_identifier(base)},
              "op" => select_json_operator(data, true),
              "right" => %{
                "Value" => %{"SingleQuotedString" => path}
              }
            }
          }
        }
    end
  end

  defp convert_keys_to_json_query(
         %{"Identifier" => %{"value" => name}},
         data,
         base
       ) do
    %{
      "Nested" => %{
        "BinaryOp" => %{
          "left" => %{"Identifier" => AstUtils.build_identifier(base)},
          "op" => select_json_operator(data, false),
          "right" => %{
            "Value" => %{"SingleQuotedString" => name}
          }
        }
      }
    }
  end

  defp select_json_operator(data, is_complex_path) do
    need_text =
      Map.get(data, :in_between, false) or Map.get(data, :in_binaryop, false) or
        Map.get(data, :in_inlist, false)

    case {is_complex_path, need_text} do
      {true, true} -> "HashLongArrow"
      {true, false} -> "HashArrow"
      {false, true} -> "LongArrow"
      {false, false} -> "Arrow"
    end
  end

  defp get_identifier_alias(%{
         "CompoundIdentifier" => [%{"value" => _join_alias}, %{"value" => key} | _]
       }) do
    key
  end

  defp get_identifier_alias(%{"Identifier" => %{"value" => name}}) do
    name
  end

  # handle literal values
  defp get_identifier_alias(%{"expr" => _, "alias" => %{"value" => name}}) do
    name
  end

  # return non-matching as is
  defp get_identifier_alias(identifier), do: identifier

  defp put_cte_scope(data, query) do
    cte_aliases =
      for tree <- get_in(query, ["with", "cte_tables"]) || [], into: %{} do
        {get_in(tree, ["alias", "name", "value"]), cte_projection_aliases(tree)}
      end

    Map.update!(data, :cte_aliases, &Map.merge(&1, cte_aliases))
  end

  defp put_query_scope(data, query) do
    data = put_cte_scope(data, query)

    case get_in(query, ["body", "Select"]) do
      %{"from" => from_list} = select when is_list(from_list) -> put_select_scope(data, select)
      _body -> data
    end
  end

  defp put_select_scope(data, %{"from" => from_list} = select) do
    from_sources = get_from_sources(from_list, data.cte_aliases)
    unnest_mappings = get_bq_unnest_mappings(from_list, from_sources)

    Map.merge(data, %{
      alias_path_mappings:
        Map.new(unnest_mappings, fn {alias_name, mapping} ->
          {alias_name, mapping.path}
        end),
      from_sources: from_sources,
      select_aliases: query_projection_aliases(%{"Select" => select}),
      unnest_mappings: unnest_mappings
    })
  end

  defp get_from_sources(from_list, cte_aliases) do
    for from <- from_list,
        table_name = get_in(from, ["relation", "Table", "name", Access.at(0), "value"]),
        is_binary(table_name),
        identifier =
          get_in(from, ["relation", "Table", "alias", "name", "value"]) || table_name,
        into: %{} do
      {identifier,
       %{
         cte?: is_map_key(cte_aliases, table_name),
         fields: Map.get(cte_aliases, table_name, []),
         table_name: table_name
       }}
    end
  end

  defp get_bq_unnest_mappings(from_list, from_sources) do
    Enum.reduce(from_list, %{}, fn from, mappings ->
      default_root =
        get_in(from, ["relation", "Table", "alias", "name", "value"]) ||
          get_in(from, ["relation", "Table", "name", Access.at(0), "value"])

      Enum.reduce(from["joins"] || [], mappings, fn join, acc ->
        process_unnest_join(join, acc, from_sources, default_root)
      end)
    end)
  end

  defp process_unnest_join(
         %{
           "relation" => %{
             "UNNEST" => %{"alias" => %{"name" => %{"value" => alias_name}}} = unnest
           }
         },
         mappings,
         from_sources,
         default_root
       ) do
    identifiers =
      case unnest do
        %{"array_expr" => expression} ->
          unnest_expression_identifiers(expression)

        %{"array_exprs" => expressions} ->
          Enum.flat_map(expressions, &unnest_expression_identifiers/1)

        _unnest ->
          []
      end

    mapping = resolve_unnest_mapping(identifiers, mappings, from_sources, default_root)
    Map.put(mappings, alias_name, mapping)
  end

  defp process_unnest_join(_join, mappings, _from_sources, _default_root), do: mappings

  defp unnest_expression_identifiers(%{"Identifier" => %{"value" => value}}), do: [value]

  defp unnest_expression_identifiers(%{"CompoundIdentifier" => identifiers}) do
    for %{"value" => value} <- identifiers, is_binary(value), do: value
  end

  defp unnest_expression_identifiers(_expression), do: []

  defp resolve_unnest_mapping([head | tail], mappings, from_sources, default_root) do
    cond do
      is_map_key(mappings, head) ->
        parent = mappings[head]
        %{root: parent.root, path: parent.path ++ tail}

      is_map_key(from_sources, head) ->
        %{root: head, path: tail}

      true ->
        %{root: default_root, path: [head | tail]}
    end
  end

  defp resolve_unnest_mapping([], _mappings, _from_sources, default_root) do
    %{root: default_root, path: []}
  end

  defp traverse_convert_identifiers({"InList" = k, v}, data) do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_inlist, true))}
  end

  defp traverse_convert_identifiers({"BinaryOp" = k, v}, data) do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_binaryop, true))}
  end

  defp traverse_convert_identifiers({"Between" = k, v}, data) do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_between, true))}
  end

  defp traverse_convert_identifiers({"Like" = k, v}, data) do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_binaryop, true))}
  end

  defp traverse_convert_identifiers({"cte_tables" = k, v}, data) do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_cte_tables_tree, true))}
  end

  defp traverse_convert_identifiers({"projection" = k, v}, data) do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_projection_tree, true))}
  end

  defp traverse_convert_identifiers({"Query" = k, v}, data) do
    {k, traverse_convert_identifiers(v, put_query_scope(data, v))}
  end

  defp traverse_convert_identifiers({"query" = k, v}, data) do
    {k, traverse_convert_identifiers(v, put_query_scope(data, v))}
  end

  defp traverse_convert_identifiers({"Select" = k, %{"from" => from_list} = v}, data)
       when is_list(from_list) do
    {k, traverse_convert_identifiers(v, put_select_scope(data, v))}
  end

  defp traverse_convert_identifiers({k, v}, data) when k in ["Function", "Cast"] do
    {k, traverse_convert_identifiers(v, Map.put(data, :in_function_or_cast, true))}
  end

  # auto set the column alias if not set
  defp traverse_convert_identifiers({"UnnamedExpr", identifier}, data)
       when is_map_key(identifier, "CompoundIdentifier") or is_map_key(identifier, "Identifier") do
    normalized_identifier = get_identifier_alias(identifier)

    if normalized_identifier do
      {"ExprWithAlias",
       %{
         "alias" => AstUtils.build_identifier(normalized_identifier),
         "expr" => traverse_convert_identifiers(identifier, data)
       }}
    else
      identifier
    end
  end

  defp traverse_convert_identifiers(
         {"CompoundIdentifier" = k, [%{"value" => head_val} | tail] = v},
         data
       )
       when tail != [] do
    cond do
      is_map_key(data.unnest_mappings, head_val) ->
        convert_unnest_reference(data.unnest_mappings[head_val], tail, data)

      is_map_key(data.from_sources, head_val) ->
        convert_source_reference(k, v, head_val, tail, data)

      is_map_key(data.cte_aliases, head_val) ->
        convert_cte_reference(k, v, head_val, tail, data)

      projected_cte_field?(head_val, data) ->
        convert_json_reference(%{"Identifier" => AstUtils.build_identifier(head_val)}, tail, data)

      true ->
        do_normal_compount_identifier_convert({k, v}, data)
    end
  end

  defp traverse_convert_identifiers({"Identifier" = k, %{"value" => field_alias} = v}, data) do
    if known_query_field?(field_alias, data) do
      {k, v}
    else
      do_normal_compount_identifier_convert({k, v}, data)
    end
  end

  # leave compound identifier as is
  defp traverse_convert_identifiers({"CompoundIdentifier" = k, v}, _data), do: {k, v}

  defp traverse_convert_identifiers({k, v}, data) when is_list(v) or is_map(v) do
    {k, traverse_convert_identifiers(v, data)}
  end

  defp traverse_convert_identifiers(kv, data) when is_list(kv) do
    Enum.map(kv, fn kv -> traverse_convert_identifiers(kv, data) end)
  end

  defp traverse_convert_identifiers(kv, data) when is_map(kv) do
    Enum.map(kv, fn kv -> traverse_convert_identifiers(kv, data) end) |> Map.new()
  end

  defp traverse_convert_identifiers(kv, _data), do: kv

  defp do_normal_compount_identifier_convert({k, v}, data) do
    convert_keys_to_json_query(%{k => v}, data)
    |> Map.to_list()
    |> List.first()
  end

  defp convert_source_reference(k, v, source_name, tail, data) do
    if data.from_sources[source_name].cte? do
      convert_cte_reference(k, v, source_name, tail, data)
    else
      case tail do
        [field] ->
          convert_keys_to_json_query(%{k => [field]}, data, [source_name, "body"])
          |> Map.to_list()
          |> List.first()

        fields ->
          convert_json_reference(
            %{
              "CompoundIdentifier" => [
                AstUtils.build_identifier(source_name),
                AstUtils.build_identifier("body")
              ]
            },
            fields,
            data
          )
      end
    end
  end

  defp convert_cte_reference(k, v, _source_name, [_field], _data) do
    {k, v}
  end

  defp convert_cte_reference(_k, _v, source_name, [field | nested_fields], data) do
    convert_json_reference(
      %{
        "CompoundIdentifier" => [
          AstUtils.build_identifier(source_name),
          AstUtils.build_identifier(field["value"])
        ]
      },
      nested_fields,
      data
    )
  end

  defp convert_unnest_reference(mapping, referenced_fields, data) do
    source = Map.get(data.from_sources, mapping.root)

    case {source, mapping.path} do
      {%{cte?: true}, [field | nested_path]} ->
        convert_json_reference(
          %{
            "CompoundIdentifier" => [
              AstUtils.build_identifier(mapping.root),
              AstUtils.build_identifier(field)
            ]
          },
          Enum.map(nested_path, &AstUtils.build_identifier/1) ++ referenced_fields,
          data
        )

      _ ->
        base =
          if mapping.root do
            %{
              "CompoundIdentifier" => [
                AstUtils.build_identifier(mapping.root),
                AstUtils.build_identifier("body")
              ]
            }
          else
            %{"Identifier" => AstUtils.build_identifier("body")}
          end

        convert_json_reference(
          base,
          Enum.map(mapping.path, &AstUtils.build_identifier/1) ++ referenced_fields,
          data
        )
    end
  end

  defp convert_json_reference(base, identifiers, data) do
    path = Enum.map(identifiers, & &1["value"])
    complex_path? = length(path) > 1

    value =
      if complex_path? do
        "{#{Enum.join(path, ",")}}"
      else
        List.first(path)
      end

    {"Nested",
     %{
       "BinaryOp" => %{
         "left" => base,
         "op" => select_json_operator(data, complex_path?),
         "right" => %{"Value" => %{"SingleQuotedString" => value}}
       }
     }}
  end

  defp projected_cte_field?(field, data) do
    cte_sources = Enum.filter(data.from_sources, fn {_name, source} -> source.cte? end)

    case cte_sources do
      [{_name, %{fields: []}}] ->
        true

      sources ->
        Enum.any?(sources, fn {_name, source} -> field in source.fields end)
    end
  end

  defp known_query_field?(field, data) do
    projected_cte_field?(field, data) or
      (data.in_projection_tree == false and field in data.select_aliases)
  end

  defp identifier?(identifier),
    do: is_map_key(identifier, "CompoundIdentifier") or is_map_key(identifier, "Identifier")

  defp numeric_value?(%{"Value" => %{"Number" => _}}), do: true
  defp numeric_value?(_), do: false

  defp json_access?(%{"Nested" => nested}), do: json_access?(nested)
  defp json_access?(%{"JsonAccess" => _}), do: true

  defp json_access?(%{"BinaryOp" => %{"op" => op}}),
    do: op in ["Arrow", "LongArrow", "HashLongArrow", "HashArrow"]

  defp json_access?(_), do: false

  defp timestamp_identifier?(%{"Identifier" => %{"value" => "timestamp"}}), do: true

  defp timestamp_identifier?(%{"CompoundIdentifier" => [_head, %{"value" => "timestamp"}]}),
    do: true

  defp timestamp_identifier?(_), do: false

  defp get_function_arg(%{"args" => %{"List" => %{"args" => args}}}, index) do
    case Enum.at(args, index) do
      %{"Unnamed" => %{"Expr" => expr}} -> expr
      _ -> nil
    end
  end

  defp get_function_arg(_, _), do: nil

  defp at_time_zone(identifier, :cast) do
    %{
      "Nested" => %{
        "AtTimeZone" => %{
          "time_zone" => %{"Value" => %{"SingleQuotedString" => "UTC"}},
          "timestamp" => %{
            "Function" => %{
              "args" => %{
                "List" => %{
                  "args" => [
                    %{
                      "Unnamed" => %{
                        "Expr" => %{
                          "BinaryOp" => %{
                            "left" => %{
                              "Cast" => %{
                                "kind" => "Cast",
                                "data_type" => %{"BigInt" => nil},
                                "expr" => identifier,
                                "format" => nil
                              }
                            },
                            "op" => "Divide",
                            "right" => %{"Value" => %{"Number" => ["1000000.0", false]}}
                          }
                        }
                      }
                    }
                  ],
                  "clauses" => [],
                  "duplicate_treatment" => nil
                }
              },
              "parameters" => "None",
              "filter" => nil,
              "uses_odbc_syntax" => false,
              "name" => [AstUtils.build_identifier("to_timestamp")],
              "null_treatment" => nil,
              "over" => nil,
              "within_group" => []
            }
          }
        }
      }
    }
  end

  defp at_time_zone(identifier, :double_colon) do
    %{
      "Nested" => %{
        "AtTimeZone" => %{
          "time_zone" => %{"Value" => %{"SingleQuotedString" => "UTC"}},
          "timestamp" => %{
            "Function" => %{
              "args" => %{
                "List" => %{
                  "args" => [
                    %{
                      "Unnamed" => %{
                        "Expr" => %{
                          "BinaryOp" => %{
                            "left" => %{
                              "Cast" => %{
                                "kind" => "DoubleColon",
                                "data_type" => %{"BigInt" => nil},
                                "expr" => identifier,
                                "format" => nil
                              }
                            },
                            "op" => "Divide",
                            "right" => %{"Value" => %{"Number" => ["1000000.0", false]}}
                          }
                        }
                      }
                    }
                  ],
                  "clauses" => [],
                  "duplicate_treatment" => nil
                }
              },
              "parameters" => "None",
              "filter" => nil,
              "uses_odbc_syntax" => false,
              "name" => [AstUtils.build_identifier("to_timestamp")],
              "null_treatment" => nil,
              "over" => nil,
              "within_group" => []
            }
          }
        }
      }
    }
  end

  defp cast_to_numeric(expr) do
    %{
      "Cast" => %{
        "kind" => "DoubleColon",
        "expr" => expr,
        "data_type" => %{"Numeric" => "None"},
        "format" => nil
      }
    }
  end

  defp cast_to_jsonb_double_colon(expr) do
    %{
      "Cast" => %{
        "kind" => "DoubleColon",
        "expr" => expr,
        "data_type" => %{
          "Custom" => [
            [AstUtils.build_identifier("jsonb")],
            []
          ]
        },
        "format" => nil
      }
    }
  end

  # Unlike CAST(... AS JSONB), to_jsonb accepts both already-JSONB values and
  # regular SQL scalar values. This matters for computed CTE columns such as
  # Studio's `level`, which is emitted by a CASE expression as TEXT.
  defp to_jsonb(expr) do
    %{
      "Function" => %{
        "args" => %{
          "List" => %{
            "args" => [%{"Unnamed" => %{"Expr" => expr}}],
            "clauses" => [],
            "duplicate_treatment" => nil
          }
        },
        "parameters" => "None",
        "filter" => nil,
        "uses_odbc_syntax" => false,
        "name" => [AstUtils.build_identifier("to_jsonb")],
        "null_treatment" => nil,
        "over" => nil,
        "within_group" => []
      }
    }
  end

  defp jsonb_to_text(expr) do
    %{
      "Nested" => %{
        "BinaryOp" => %{
          "left" => expr,
          "op" => "HashLongArrow",
          "right" => %{
            "Value" => %{"SingleQuotedString" => "{}"}
          }
        }
      }
    }
  end
end
