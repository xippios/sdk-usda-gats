- The client's cache keeps every answer, where it kept five lists: a Census month for five
  minutes, core's default, the Census release lists for an hour as before, and every UN
  Trade answer and the HS10 list for a day, so a narrower filter on a month or a
  reporter-year already read sends no request. A month that Census revises within those
  five minutes keeps its earlier figures until the entry expires, and an answer larger than
  16 MiB, as India's 2016 UN Trade exports, is not stored. (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-gats/issues/42, https://github.com/xippios/sdk-usda-gats/issues/57)
