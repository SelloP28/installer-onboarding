import unittest

from token_utils import parse_access_token


class ParseAccessTokenTests(unittest.TestCase):
    token = "123e4567-e89b-12d3-a456-426614174000"

    def test_parses_raw_uuid(self):
        self.assertEqual(parse_access_token(self.token), self.token)

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(parse_access_token(f"  {self.token}  "), self.token)

    def test_normalizes_uppercase_uuid(self):
        self.assertEqual(parse_access_token(self.token.upper()), self.token)

    def test_parses_full_url(self):
        url = f"https://x.streamlit.app/?access_token={self.token}"
        self.assertEqual(parse_access_token(url), self.token)

    def test_parses_url_with_other_parameters(self):
        url = f"https://x.streamlit.app/?source=email&access_token={self.token}&next=home"
        self.assertEqual(parse_access_token(url), self.token)

    def test_parses_query_string(self):
        query = f"source=email&access_token={self.token}&next=home"
        self.assertEqual(parse_access_token(query), self.token)

    def test_rejects_empty_string(self):
        self.assertIsNone(parse_access_token(""))

    def test_rejects_random_text(self):
        self.assertIsNone(parse_access_token("not a token"))

    def test_rejects_uuid_like_string_with_wrong_length(self):
        self.assertIsNone(parse_access_token("123e4567-e89b-12d3-a456-42661417400"))


if __name__ == "__main__":
    unittest.main()
