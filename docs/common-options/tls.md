---
title: TLS (Transport Layer Security)
parent: Configuring MQTTPublish
nav_order: 1
---

## The `[[tls]]` section

The TLS options that are passed to tls_set method of the MQTT client.
For additional information see,
[https://eclipse.org/paho/clients/python/docs/strptime-format-codes](https://eclipse.org/paho/clients/python/docs/strptime-format-codes)

### enable

Whether `tls` is enabled or not.
Valid values are `true` or `false`.
The default value is `true`.

### ca_certs

Path to the Certificate Authority certificate files that are to be treated as trusted by this client.

### certfile

The PEM encoded client certificate and private keys.
The default value is `None`.

### certs_required

The certificate requirements that the client imposes on the broker.
Valid values are `none`, `optional`, or `required`.
The default value is `required`.

### ciphers

The encryption ciphers that are allowable for this connection.
Specify `None` to use the defaults.
The default value is `None`.

### keyfile

The private keys.
The default value is `None`.

### tls_version

The version of the SSL/TLS protocol to be used.
Valid values are `sslv2`, `sslv23`, `sslv3`, `tls`, `tlsv1`, `tlsv11`, or `tlsv12`.
The default value is `tlsv12`.
