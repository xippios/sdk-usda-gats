- The tests that serve GATS's empty answer at a URL that no recording holds assert only what
  the call sent and what the task adds to the answer, never a whole field that rows would
  change, as sdk-core's conventions §10 allow. A caller sees no change.
  (https://github.com/xippios/sdk-usda-gats/issues/74)
