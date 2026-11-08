#include "src/net.h"

const char *net_scheme(void) {
#if ENABLE_HTTPS
    return "https";
#else
    return "http";
#endif
}
