#!/usr/bin/env python
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A script to convert Bazel build systems to CMakeLists.txt.

See README.md for more information.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys
import textwrap
import ast
import os
from glob import glob
from pathlib import Path


def StripColons(deps):
    return [item.replace(":", "") for item in deps]


def GetTargetName(names):
    ret_val = []
    for item in names:
        if ":" in item:
            ret_val.append(item[item.rfind(":")+1:])
        elif "/" in item:
            ret_val.append(item[item.rfind("/")+1:])
        else:
            ret_val.append(item)
    return ret_val


def IsSourceFile(name):
    endings = [".c", ".cc", ".cpp"]
    return any(n in name for n in endings)


class BuildFileFunctions(object):
    def __init__(self, converter):
        self.converter = converter
        self.globs = {}  # needed to expand global vars on the fly, i.e. through load()

    def _append_toplevel(self, string):
        self.converter.append_current_toplevel(string)

    def _add_deps(self, kwargs, keyword=""):
        if "deps" not in kwargs:
            return
        string = "target_link_libraries(%s%s\n  %s)\n" % (
            kwargs["name"],
            keyword,
            # "\n  ".join(StripColons(kwargs["deps"]))
            "\n  ".join(GetTargetName(kwargs["deps"]))
        )
        self._append_toplevel(string)

    def _target_include_directories(self, **kwargs):
        copts = kwargs.get("copts", [])

        for opt in copts:
            if opt.startswith("-I"):
                string = "target_include_directories(%s PUBLIC %s)\n" % (
                    kwargs["name"],
                    opt[2:],
                )
                self._append_toplevel(string)

    def load(self, file, *args):
        file = file.replace("//:", "./")
        with open(file, 'r') as f:
            prev_dir = dir()
            exec(f.read())
            delta_dir = [item for item in dir() if item not in prev_dir]
            delta_dir.remove("prev_dir")

            for var in delta_dir:
                self.globs[var] = eval(var)

    def cc_library(self, **kwargs):
        if kwargs["name"] == "amalgamation" or kwargs["name"] == "upbc_generator":
            return
        files = kwargs.get("srcs", []) + kwargs.get("hdrs", [])

        if True or filter(IsSourceFile, files):
            # Has sources, make this a normal library.
            string = "add_library(%s\n  %s)\n" % (
                kwargs["name"],
                "\n  ".join(files)
            )
            self._append_toplevel(string)
            self._add_deps(kwargs)

            self._target_include_directories(**kwargs)

            string = "SET_TARGET_PROPERTIES(%s PROPERTIES LINKER_LANGUAGE CXX)\n" % kwargs[
                "name"]
            self._append_toplevel(string)

        else:
            # Header-only library, have to do a couple things differently.
            # For some info, see:
            #  http://mariobadr.com/creating-a-header-only-library-with-cmake.html
            string = "add_library(%s INTERFACE)\n" % (
                kwargs["name"]
            )
            self._append_toplevel(string)

            # TODO: if it is a relative path, its not allowed with target_sources. Maybe with include_...?
            string = "target_sources(%s INTERFACE\n %s)\n" % (
                kwargs["name"],
                # "\n  ".join(StripColons(files))
                "\n  ".join(files)
            )
            self._append_toplevel(string)
            self._add_deps(kwargs, " INTERFACE")

    def cc_binary(self, **kwargs):
        files = kwargs.get("srcs", []) + kwargs.get("hdrs", [])

        string = "add_executable(%s\n  %s)\n" % (
            kwargs["name"],
            "\n  ".join(files)
        )
        self._append_toplevel(string)
        self._add_deps(kwargs)

        self._target_include_directories(**kwargs)

    def cc_test(self, **kwargs):
        # Disable this until we properly support upb_proto_library().
        string = "add_executable(%s\n  %s)\n" % (
            kwargs["name"],
            "\n  ".join(kwargs["srcs"])
        )
        self._append_toplevel(string)

        string = "add_test(NAME %s COMMAND %s)\n" % (
            kwargs["name"],
            kwargs["name"],
        )
        self._append_toplevel(string)

        if "data" in kwargs:
            for data_dep in kwargs["data"]:
                string = textwrap.dedent("""\
              add_custom_command(
                  TARGET %s POST_BUILD
                  COMMAND ${CMAKE_COMMAND} -E copy
                          ${CMAKE_SOURCE_DIR}/%s
                          ${CMAKE_CURRENT_BINARY_DIR}/%s)\n""" % (
                    kwargs["name"], data_dep, data_dep
                ))
                self._append_toplevel(string)

        self._add_deps(kwargs)

        self._target_include_directories(**kwargs)

    def py_library(self, **kwargs):
        pass

    def py_binary(self, **kwargs):
        pass

    def lua_cclibrary(self, **kwargs):
        pass

    def lua_library(self, **kwargs):
        pass

    def lua_binary(self, **kwargs):
        pass

    def lua_test(self, **kwargs):
        pass

    def sh_test(self, **kwargs):
        pass

    def make_shell_script(self, **kwargs):
        pass

    def exports_files(self, files, **kwargs):
        pass

    def proto_library(self, **kwargs):
        pass

    def generated_file_staleness_test(self, **kwargs):
        pass

    def upb_amalgamation(self, **kwargs):
        pass

    def upb_proto_library(self, **kwargs):
        pass

    def upb_proto_reflection_library(self, **kwargs):
        pass

    def genrule(self, **kwargs):
        pass

    def config_setting(self, **kwargs):
        pass

    def select(self, arg_dict):
        return []

    def glob(self, *args):
        return []

    def licenses(self, *args):
        pass

    def map_dep(self, arg):
        return arg

    def package(self, **kwargs):
        pass


class WorkspaceFileFunctions(object):
    def __init__(self, converter):
        self.converter = converter

    def load(self, file, *args):
        pass

    def workspace(self, **kwargs):
        self.converter.prelude += "project(%s C CXX)\n" % (kwargs["name"])

    def http_archive(self, **kwargs):
        pass

    def git_repository(self, **kwargs):
        pass

    def new_local_repository(self, **kwargs):
        pass


class Converter(object):
    def __init__(self):
        self.prelude = ""
        self.toplevel = {}
        self.include_subdirs = {}
        self.if_lua = ""
        self.current_build_file = ""

    def append_current_toplevel(self, string):
        if self.current_build_file not in self.toplevel:
            self.toplevel[self.current_build_file] = ""

        self.toplevel[self.current_build_file] = self.toplevel[self.current_build_file] + string

    def append_current_subdir(self, file):
        if self.current_build_file not in self.include_subdirs:
            self.include_subdirs[self.current_build_file] = []

        self.include_subdirs[self.current_build_file].append(file)

    def convert_prelude(self):
        return self.prelude_template % {"prelude": self.prelude}

    def convert_toplevel(self):
        include_dirs = ""
        if self.current_build_file in self.include_subdirs:
            for directory in self.include_subdirs[self.current_build_file]:
                include_dirs += "add_subdirectory(%s)\n" % directory.replace(
                    ".", "").replace("/", "")
        return "%s\n%s" % (include_dirs, self.toplevel[self.current_build_file])

    prelude_template = textwrap.dedent("""\
    # This file was generated from BUILD using tools/make_cmakelists.py.

    cmake_minimum_required(VERSION 3.1)

    if(${CMAKE_VERSION} VERSION_LESS 3.12)
        cmake_policy(VERSION ${CMAKE_MAJOR_VERSION}.${CMAKE_MINOR_VERSION})
    else()
        cmake_policy(VERSION 3.12)
    endif()

    cmake_minimum_required (VERSION 3.0)
    cmake_policy(SET CMP0048 NEW)

    %(prelude)s

    SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++17")

    # Prevent CMake from setting -rdynamic on Linux (!!).
    SET(CMAKE_SHARED_LIBRARY_LINK_C_FLAGS "")
    SET(CMAKE_SHARED_LIBRARY_LINK_CXX_FLAGS "")

    # Set default build type.
    if(NOT CMAKE_BUILD_TYPE)
      message(STATUS "Setting build type to 'RelWithDebInfo' as none was specified.")
      set(CMAKE_BUILD_TYPE "RelWithDebInfo" CACHE STRING
          "Choose the type of build, options are: Debug Release RelWithDebInfo MinSizeRel."
          FORCE)
    endif()

    # When using Ninja, compiler output won't be colorized without this.
    include(CheckCXXCompilerFlag)
    CHECK_CXX_COMPILER_FLAG(-fdiagnostics-color=always SUPPORTS_COLOR_ALWAYS)
    if(SUPPORTS_COLOR_ALWAYS)
      set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fdiagnostics-color=always")
    endif()

    # Implement ASAN/UBSAN options
    if(UPB_ENABLE_ASAN)
      set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=address")
      set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fsanitize=address")
      set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=address")
      set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -fsanitize=address")
    endif()

    if(UPB_ENABLE_UBSAN)
      set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=undefined")
      set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fsanitize=address")
      set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=address")
      set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -fsanitize=address")
    endif()

    #include_directories(.)
    #include_directories(${CMAKE_CURRENT_BINARY_DIR})

    if(APPLE)
      set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -undefined dynamic_lookup -flat_namespace")
    elseif(UNIX)
      set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--build-id")
    endif()

    enable_testing()


    """)

    def convert(self):
        return self.convert_prelude() + self.convert_toplevel()


data = {}
converter = Converter()


def GetDict(obj):
    ret = {}
    for k in dir(obj):
        # if k == "variables":
        #    for v in obj.variables:
        #        ret[v] = getattr(obj.variables, v)
        if not k.startswith("_"):
            ret[k] = getattr(obj, k)
    return ret


def ParseBuildFile(path, converter):
    cmake_created = False

    for directory in glob(path+"*/"):
        if not os.path.islink(Path(directory)):
            cmake_created_in_dir = ParseBuildFile(directory, converter)
            if cmake_created_in_dir:
                cmake_created = True
                converter.current_build_file = os.path.join(path, "BUILD")
                converter.append_current_subdir(directory)

    if "BUILD" in os.listdir(path):
        file = os.path.join(path, "BUILD")
        converter.current_build_file = file
        code_block = compile(open(file).read(), file, 'exec')
        build = BuildFileFunctions(converter)
        code_globals = GetDict(build)
        build.globs = code_globals
        exec(code_block, code_globals)
        return True

    return cmake_created


globs = GetDict(converter)

exec(open("WORKSPACE").read(), GetDict(WorkspaceFileFunctions(converter)))

ParseBuildFile("./", converter)

to_create_files = set(converter.include_subdirs.keys())
to_create_files.update(set(converter.toplevel.keys()))

for affected_subdirs in to_create_files:
    with open(affected_subdirs.replace("BUILD", sys.argv[1]), "w") as f:
        converter.current_build_file = affected_subdirs
        if "./BUILD" == affected_subdirs:
            f.write(converter.convert())
        else:
            f.write(converter.convert_toplevel())

# with open(sys.argv[1], "w") as f:
#    f.write(converter.convert())
