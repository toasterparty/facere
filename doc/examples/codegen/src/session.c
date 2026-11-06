#include "messages/login.h"

int session_open(const char *user, int attempt)
{
    struct login message = { user, attempt };
    return login_validate(&message);
}
