# דיאגרמת מחלקות: היררכיית השגיאות

```mermaid
classDiagram
    direction TB

    class Exception {
        <<Python>>
    }

    class AuthError {
        +str detail
    }
    class ForbiddenError {
        +str detail
    }
    class NotFoundError {
        +str detail
    }
    class ConflictError {
        +str detail
    }
    class ExternalServiceError {
        +str detail
    }

    class ExceptionHandlers {
        +register_exception_handlers(app)
        -_auth_error_handler(request, exc) JSONResponse
        -_forbidden_error_handler(request, exc) JSONResponse
        -_not_found_error_handler(request, exc) JSONResponse
        -_conflict_error_handler(request, exc) JSONResponse
        -_external_service_error_handler(request, exc) JSONResponse
    }

    Exception <|-- AuthError
    Exception <|-- ForbiddenError
    Exception <|-- NotFoundError
    Exception <|-- ConflictError
    Exception <|-- ExternalServiceError

    ExceptionHandlers ..> AuthError : 401
    ExceptionHandlers ..> ForbiddenError : 403
    ExceptionHandlers ..> NotFoundError : 404
    ExceptionHandlers ..> ConflictError : 409
    ExceptionHandlers ..> ExternalServiceError : 502
```

*היררכיית השגיאות: חמש המשפחות יורשות ישירות מ-`Exception` של Python, ולכל אחת מהן מטפל
אחד המחזיר קוד תשובה קבוע. 39 הטיפוסים הקונקרטיים יורשים מן המשפחות ומפורטים בטבלה שבסוף
הסעיף.*
