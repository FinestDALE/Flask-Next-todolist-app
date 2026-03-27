from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from AppCreator import AppCreator
from ApiRequest import (
    ApiRequests,
    ApplicationServices,
    MongoAuthRepository,
    MongoDatabase,
    MongoTaskRepository,
    applyTaskUpdates,
    buildSessionResponse,
    buildSummary,
    clearSessionCookie,
    createTaskRecord,
    ensureStore,
    getServices as _getServices,
    responsePayload,
    saveStore,
    sessionPayload,
    sortTasks,
    validationErrorResponse,
)
from Object import (
    AuthChangePasswordPayload,
    AuthLoginPayload,
    AuthRegisterPayload,
    AuthenticatedSession,
    MongoCollections,
    SessionUser,
    Task,
    TaskCreate,
    TaskStore,
    TaskUpdate,
    allowedDevOrigins,
    defaultCategory,
    defaultMongoDb,
    defaultMongoUri,
    defaultPriority,
    defaultSessionCollection,
    defaultStore,
    defaultTaskCollection,
    defaultTitle,
    defaultUserCollection,
    ensureUtcAwareDateTime,
    fallbackValue,
    normalizeDueValue,
    normalizeEmailValue,
    normalizePriorityValue,
    normalizeTextValue,
    nowIso,
    nowUtc,
    sessionCookieName,
    sessionDurationDays,
    validateDueDate,
    validateDueDateTime,
)


def getServices() -> ApplicationServices:
    return _getServices()


app = AppCreator(apiRequests=ApiRequests(services_provider=lambda: getServices())).create_app()


if __name__ == "__main__":
    app.run(debug=True)
