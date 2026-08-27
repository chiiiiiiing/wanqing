idf_component_register(
    SRCS
        "src/agent_link.cpp"
        "src/transport_ble.cpp"
        "src/transport_wifi.cpp"
        "src/wifi_provision.cpp"
        "src/protocol.cpp"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "src"
    REQUIRES esp_common
    PRIV_REQUIRES log bt nvs_flash freertos
                  esp_wifi esp_netif esp_event esp_http_server esp_timer lwip
    EMBED_TXTFILES "portal/portal.html" "portal/connecting.html"
)

# Aggregate members omitted by the protocol tables are intentionally
# zero-initialized. Keep GCC 14's stricter diagnostic from becoming an error.
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-missing-field-initializers)
