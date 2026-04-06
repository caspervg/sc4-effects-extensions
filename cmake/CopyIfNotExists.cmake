if(NOT DEFINED SRC)
    message(FATAL_ERROR "SRC is required")
endif()

if(NOT DEFINED DST)
    message(FATAL_ERROR "DST is required")
endif()

if(NOT EXISTS "${DST}")
    get_filename_component(DST_DIR "${DST}" DIRECTORY)
    file(MAKE_DIRECTORY "${DST_DIR}")
    file(COPY_FILE "${SRC}" "${DST}")
endif()

