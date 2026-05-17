#include <gtest/gtest.h>
#include <regex>

#include "pluton/version.h"

TEST(VersionTest, ReturnsNonEmptyString) {
    EXPECT_FALSE(pluton::version().empty());
}

TEST(VersionTest, MatchesSemverPattern) {
    const std::string v = pluton::version();
    const std::regex semver_pattern{R"(^\d+\.\d+\.\d+$)"};
    EXPECT_TRUE(std::regex_match(v, semver_pattern))
        << "Expected MAJOR.MINOR.PATCH, got: " << v;
}
