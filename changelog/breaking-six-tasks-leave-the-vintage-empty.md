- The six tasks that read another flow's release list, `get_census_reexports`,
  `get_census_reexport_series`, the three customs-district tasks and `get_un_reexports`,
  leave `meta.vintage` and `meta.published_at` empty, where they held the release time of
  the Census or UN Trade exports or imports, which states no release of the data they
  answer. They still refuse a month or a reporter-year that the list lacks, and the refusal
  names the list that was read and the assumption that it holds for their data.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474, https://github.com/xippios/sdk-usda-gats/issues/55)
